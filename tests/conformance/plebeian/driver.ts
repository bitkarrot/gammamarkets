/**
 * Plebeian conformance driver — run inside a PINNED PlebeianApp/market
 * clone via bun:
 *
 *   bun .conformance/matrix_driver.ts '<params-json>'
 *
 * Everything is driven through Plebeian's own modules — NDK store wiring,
 * the real checkout path (`publishOrderWithDependencies` in
 * src/publish/orders.tsx), and the strict dual-copy rumor transport
 * (`publishNip17OrderTransportMessage` in
 * src/lib/orders/nip17OrderTransport.ts). No extension-side shortcuts:
 * the script publishes exactly what the real client publishes.
 *
 * Params (JSON argv[2]):
 *   mode            "real-checkout" | "strict-rumor" | "read-wraps"
 *   relay           ws:// URL of the local nak relay
 *   buyerSecretHex  buyer private key (hex)
 *   merchantPubkey  merchant pubkey (hex)
 *   -- real-checkout --
 *   shippingData    CheckoutFormData fields (name, email, address lines…)
 *   productsBySeller / sellerData / v4vShares   per publishOrderWithDependencies
 *   -- strict-rumor --
 *   orderId / productRef / amountSats           type-1 rumor fields
 *   -- read-wraps --
 *   (reads kind-1059 wraps addressed to the buyer and unwraps them)
 *
 * Output: a single JSON line on stdout prefixed with `MATRIX_RESULT `
 * carrying mode-specific evidence (published event ids/kinds, rumor ids,
 * transport attempts, unwrapped payment tags).
 */
import { NDKPrivateKeySigner, NDKEvent, type NDKFilter } from '@nostr-dev-kit/ndk'
import { finalizeEvent } from 'nostr-tools'
import { configActions } from '@/lib/stores/config'
import { ndkActions, ndkStore } from '@/lib/stores/ndk'
import { createPrivateKeySigner, setSignerCapability } from '@/lib/nostr/signer-registry'
import { publishOrderWithDependencies } from '@/publish/orders'
import { createOrderCreationRumor } from '@/lib/orders/orderMessageRumor'
import { publishNip17OrderTransportMessage } from '@/lib/orders/nip17OrderTransport'
import { unwrapNip17OrderMessages } from '@/lib/orders/nip17OrderRead'
import { NIP59_GIFT_WRAP_KIND } from '@/lib/nostr/nip59'

type Params = Record<string, any>

const params: Params = JSON.parse(process.argv[2] ?? '{}')
const RELAY: string = params.relay

function emit(result: Record<string, unknown>): void {
	console.log('MATRIX_RESULT ' + JSON.stringify(result))
}

async function main(): Promise<void> {
	const buyerSecret: Uint8Array = Uint8Array.from(Buffer.from(params.buyerSecretHex, 'hex'))

	configActions.setConfig({
		stage: 'development',
		appRelay: RELAY,
		externalZapRelaysEnabled: false,
	} as any)

	const ndk = ndkActions.initialize([RELAY])
	const signer = new NDKPrivateKeySigner(params.buyerSecretHex)
	const user = await signer.user()
	const buyerPubkey = user.pubkey
	ndkActions.publishSigner(signer, user)
	setSignerCapability(createPrivateKeySigner(params.buyerSecretHex))
	await ndkActions.connect(8000)

	// Evidence tap: record every event the Plebeian stack publishes.
	const published: any[] = []
	const realPublish = ndkActions.publishEvent.bind(ndkActions)
	;(ndkActions as any).publishEvent = async (event: NDKEvent, relaySet?: any) => {
		const res = await realPublish(event, relaySet)
		published.push({
			kind: event.kind,
			id: event.id,
			pubkey: event.pubkey,
			tags: event.tags.map((t: string[]) => t.slice(0, 3)),
			created_at: event.created_at,
		})
		return res
	}

	// Buyer inbox advertisement (kind-10050) — required both for the
	// extension's peer_relays discovery and for the strict transport's
	// sender-copy target resolution.
	const listEvent = finalizeEvent(
		{
			kind: 10050,
			content: '',
			created_at: Math.floor(Date.now() / 1000),
			tags: [['relay', RELAY]],
		},
		buyerSecret,
	)
	const listPublish = await ndkActions.publishEvent(new NDKEvent(ndk, listEvent))
	published.push({ kind: 10050, id: listEvent.id, pubkey: listEvent.pubkey, tags: listEvent.tags })

	if (params.mode === 'real-checkout') {
		const orderIds = await publishOrderWithDependencies({
			shippingData: params.checkout.shippingData,
			sellers: [params.merchantPubkey],
			productsBySeller: params.checkout.productsBySeller,
			sellerData: params.checkout.sellerData,
			v4vShares: params.checkout.v4vShares ?? {},
		})
		emit({ mode: params.mode, buyerPubkey, orderIds, published })
		return
	}

	if (params.mode === 'strict-rumor') {
		const rumor = createOrderCreationRumor({
			buyerPubkey,
			merchantPubkey: params.merchantPubkey,
			orderId: params.orderId,
			amountSats: params.amountSats,
			items: [{ productRef: params.productRef, quantity: 1 }],
		})
		const capability = createPrivateKeySigner(params.buyerSecretHex)
		const result = await publishNip17OrderTransportMessage({
			rumor,
			signer: capability,
			fetchRelayListEvents: async ({ pubkey }) => {
				const filter: NDKFilter = { kinds: [10050], authors: [pubkey], limit: 1 }
				const events = await ndk.fetchEvents(filter)
				return Array.from(events).map((e) => ({
					id: e.id,
					kind: e.kind,
					pubkey: e.pubkey,
					created_at: e.created_at ?? 0,
					tags: e.tags.map((t) => [...t]),
					content: e.content,
				}))
			},
			publishGiftWrap: async ({ giftWrap }) => {
				const res = await ndkActions.publishEvent(new NDKEvent(ndk, giftWrap))
				return res
			},
		})
		emit({ mode: params.mode, buyerPubkey, rumorId: rumor.id, transport: result, published })
		return
	}

	if (params.mode === 'read-wraps') {
		const filter: NDKFilter = { kinds: [NIP59_GIFT_WRAP_KIND], '#p': [buyerPubkey] }
		const wraps = await ndk.fetchEvents(filter)
		const capability = createPrivateKeySigner(params.buyerSecretHex)
		const messages: any[] = []
		for (const wrap of wraps) {
			try {
				const out = await unwrapNip17OrderMessages({
					giftWraps: [wrap.rawEvent() as any],
					signer: capability,
				})
				for (const m of out) {
					messages.push({
						wrapId: wrap.id,
						direction: m.direction,
						rumorId: m.rumor.id,
						kind: m.rumor.kind,
						tags: m.rumor.tags,
						content: m.rumor.content,
					})
				}
			} catch (error) {
				messages.push({ wrapId: wrap.id, error: String(error) })
			}
		}
		emit({ mode: params.mode, buyerPubkey, wrapCount: wraps.size, messages })
		return
	}

	emit({ error: `unknown mode ${params.mode}` })
	process.exit(2)
}

main()
	.then(() => process.exit(0))
	.catch((error) => {
		console.error('matrix driver failed:', error)
		emit({ error: String(error?.message ?? error) })
		process.exit(1)
	})
