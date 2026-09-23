/* admin_orders.js — B1 order workspace (sketch 002-A Linear Split).

   390px searchable/filterable list + persistent detail pane. Legal
   actions only — derived from the §7.1/§7.2 tables; illegal transitions
   are never offered (hidden or disabled with a reason). */
(function () {
  "use strict";

  var STATE_FILTERS = [
    { value: "", label: "All" },
    { value: "awaiting_payment", label: "Awaiting payment" },
    { value: "confirmed", label: "Confirmed" },
    { value: "needs_attention", label: "Needs attention" },
    { value: "expired", label: "Expired" },
    { value: "cancelled", label: "Cancelled" }
  ];

  var STATE_LABELS = {
    received: "Received",
    invoice_pending: "Invoice pending",
    awaiting_payment: "Awaiting payment",
    confirmed: "Confirmed",
    processing: "Processing",
    completed: "Completed",
    rejected: "Rejected",
    expired: "Expired",
    cancelled: "Cancelled"
  };

  var CHANNEL_LABELS = { web: "Web", gamma: "Gamma", nip15: "NIP-15" };

  window.app.mixin({
    data: function () {
      return {
        gmOrders: {
          loading: false,
          error: null,
          list: [],
          q: "",
          stateFilter: "",
          selectedId: null,
          detail: null,
          events: [],
          detailLoading: false,
          detailError: null,
          mobileDetail: false,
          stateFilters: STATE_FILTERS,
          actionError: null,
          cancelDialog: { show: false, reason: "", busy: false },
          shipDialog: {
            show: false, target: "", tracking: "", carrier: "", eta: "",
            busy: false
          },
          refundDialog: { show: false, reference: "", busy: false },
          reissue: { show: false, link: "" }
        }
      };
    },
    computed: {
      gmOrdersSummary: function () {
        var active = this.gmOrders.list.filter(function (o) {
          return ["completed", "rejected", "cancelled", "expired"].indexOf(
            o.state
          ) === -1;
        }).length;
        var attention = this.gmOrders.list.filter(function (o) {
          return o.payment_exception || o.oversold;
        }).length;
        return active + " active orders · " + attention + " need attention";
      },
      gmOrderActions: function () {
        /* §7.1/§7.2 legal-action map — only legal controls render; the
           terminal state renders a disabled control with the reason. */
        var d = this.gmOrders.detail;
        if (!d) return [];
        var out = [];
        if (d.payment_exception) {
          out.push(
            { key: "accept", label: "Accept paid order", kind: "exception" },
            { key: "refund", label: "Request refund", kind: "exception" },
            {
              key: "confirm-refund",
              label: "Confirm refund sent",
              kind: "exception"
            }
          );
          return out;
        }
        switch (d.state) {
          case "confirmed":
            out.push({
              key: "status:processing",
              label: "Start processing",
              kind: "primary"
            });
            out.push({
              key: "cancel",
              label: "Cancel with reason",
              kind: "danger"
            });
            break;
          case "processing":
            /* §7.2 shipping transitions: pending→processing,
               processing/exception→shipped, shipped→delivered. */
            if (d.shipping_state === "pending") {
              out.push({
                key: "ship:processing",
                label: "Start fulfillment",
                kind: "secondary"
              });
            } else if (d.shipping_state === "processing" ||
                       d.shipping_state === "exception") {
              out.push({
                key: "ship:shipped",
                label: "Mark shipped",
                kind: "primary"
              });
            } else if (d.shipping_state === "shipped") {
              out.push({
                key: "ship:delivered",
                label: "Mark delivered",
                kind: "primary"
              });
            }
            out.push({
              key: "status:completed",
              label: "Mark complete",
              kind: "secondary"
            });
            out.push({
              key: "cancel",
              label: "Cancel with reason",
              kind: "danger"
            });
            break;
          case "awaiting_payment":
          case "invoice_pending":
          case "received":
            out.push({ key: "cancel", label: "Cancel", kind: "danger" });
            break;
          default:
            out.push({
              key: "none",
              label: "No legal action",
              kind: "disabled",
              reason: "This order is in a terminal state."
            });
        }
        if (d.protocol === "web") {
          out.push({
            key: "reissue",
            label: "Reissue status link",
            kind: "secondary"
          });
        }
        return out;
      }
    },
    methods: {
      gmOrderStateLabel: function (s) {
        return STATE_LABELS[s] || s;
      },
      gmChannelLabel: function (p) {
        return CHANNEL_LABELS[p] || p;
      },
      gmLoadOrders: async function () {
        var self = this;
        var mid = self.gmMerchantId();
        if (!mid) return;
        self.gmOrders.loading = true;
        self.gmOrders.error = null;
        try {
          var params = [];
          if (self.gmOrders.stateFilter) {
            params.push("state=" + self.gmOrders.stateFilter);
          }
          if (self.gmOrders.q) {
            params.push("q=" + encodeURIComponent(self.gmOrders.q));
          }
          var qs = params.length ? "?" + params.join("&") : "";
          self.gmOrders.list = await self.gmApi(
            "GET", "/merchants/" + mid + "/orders" + qs
          );
        } catch (e) {
          self.gmOrders.error = self.gmProblemCopy(e.problem);
        }
        self.gmOrders.loading = false;
      },
      gmSelectOrder: async function (id) {
        var self = this;
        self.gmOrders.selectedId = id;
        self.gmOrders.mobileDetail = true;
        self.gmOrders.detailLoading = true;
        self.gmOrders.detailError = null;
        self.gmOrders.actionError = null;
        var mid = self.gmMerchantId();
        try {
          var pair = await Promise.all([
            self.gmApi("GET", "/merchants/" + mid + "/orders/" + id),
            self.gmApi("GET", "/merchants/" + mid + "/orders/" + id + "/events")
          ]);
          self.gmOrders.detail = pair[0];
          self.gmOrders.events = pair[1];
        } catch (e) {
          self.gmOrders.detailError = self.gmProblemCopy(e.problem);
        }
        self.gmOrders.detailLoading = false;
      },
      gmOrderBack: function () {
        /* ≤560px: detail → list navigation ("← Back to orders"). */
        this.gmOrders.mobileDetail = false;
      },
      gmDoAction: async function (action) {
        var self = this;
        var mid = self.gmMerchantId();
        var id = self.gmOrders.selectedId;
        self.gmOrders.actionError = null;
        try {
          if (action.key === "cancel") {
            self.gmOrders.cancelDialog = {
              show: true, reason: "", busy: false
            };
            return;
          }
          if (action.key.indexOf("ship:") === 0) {
            self.gmOrders.shipDialog = {
              show: true,
              target: action.key.split(":")[1],
              tracking: "", carrier: "", eta: "", busy: false
            };
            return;
          }
          if (action.key === "refund") {
            self.gmOrders.refundDialog = {
              show: false, reference: "", busy: true
            };
            await self.gmResolve("refund", null);
            return;
          }
          if (action.key === "confirm-refund") {
            self.gmOrders.refundDialog = {
              show: true, reference: "", busy: false
            };
            return;
          }
          if (action.key === "accept") {
            await self.gmResolve("accept", null);
            return;
          }
          if (action.key === "reissue") {
            var res = await self.gmApi(
              "POST",
              "/merchants/" + mid + "/orders/" + id +
                "/public-token/reissue",
              {}
            );
            self.gmOrders.reissue = {
              show: true,
              /* The new link is shown ONCE — old token revoked already. */
              link: "/gammamarkets/order#" + res.public_token
            };
            return;
          }
          if (action.key.indexOf("status:") === 0) {
            await self.gmApi(
              "POST",
              "/merchants/" + mid + "/orders/" + id + "/status",
              { to_state: action.key.split(":")[1] }
            );
            await self.gmSelectOrder(id);
            await self.gmLoadOrders();
          }
        } catch (e) {
          self.gmOrders.actionError = self.gmProblemCopy(e.problem);
        }
      },
      gmResolve: async function (action, refundRef) {
        var self = this;
        var mid = self.gmMerchantId();
        var id = self.gmOrders.selectedId;
        var body = { action: action };
        if (refundRef) body.refund_reference = refundRef;
        await self.gmApi(
          "POST",
          "/merchants/" + mid + "/orders/" + id + "/resolve-exception",
          body
        );
        await self.gmSelectOrder(id);
        await self.gmLoadOrders();
      },
      gmCancelConfirm: async function () {
        var self = this;
        if (!self.gmOrders.cancelDialog.reason.trim()) return;
        self.gmOrders.cancelDialog.busy = true;
        var mid = self.gmMerchantId();
        var id = self.gmOrders.selectedId;
        try {
          await self.gmApi(
            "POST",
            "/merchants/" + mid + "/orders/" + id + "/cancel",
            { reason: self.gmOrders.cancelDialog.reason.trim() }
          );
          self.gmOrders.cancelDialog.show = false;
          await self.gmSelectOrder(id);
          await self.gmLoadOrders();
        } catch (e) {
          self.gmOrders.actionError = self.gmProblemCopy(e.problem);
        }
        self.gmOrders.cancelDialog.busy = false;
      },
      gmShipConfirm: async function () {
        var self = this;
        self.gmOrders.shipDialog.busy = true;
        var mid = self.gmMerchantId();
        var id = self.gmOrders.selectedId;
        var d = self.gmOrders.shipDialog;
        var body = { shipping_state: d.target };
        if (d.tracking.trim()) body.tracking = d.tracking.trim();
        if (d.carrier.trim()) body.carrier = d.carrier.trim();
        if (d.eta.trim()) body.eta = d.eta.trim();
        try {
          await self.gmApi(
            "POST",
            "/merchants/" + mid + "/orders/" + id + "/shipping",
            body
          );
          self.gmOrders.shipDialog.show = false;
          await self.gmSelectOrder(id);
          await self.gmLoadOrders();
        } catch (e) {
          self.gmOrders.actionError = self.gmProblemCopy(e.problem);
        }
        self.gmOrders.shipDialog.busy = false;
      },
      gmRefundConfirm: async function () {
        var self = this;
        self.gmOrders.refundDialog.busy = true;
        try {
          await self.gmResolve(
            "confirm-refund",
            self.gmOrders.refundDialog.reference.trim() || null
          );
          self.gmOrders.refundDialog.show = false;
        } catch (e) {
          self.gmOrders.actionError = self.gmProblemCopy(e.problem);
        }
        self.gmOrders.refundDialog.busy = false;
      }
    },
    mounted: function () {
      /* Wire once, on the app root — mixin hooks run per component and
         a leaf's gm is a different object than the root's (the one the
         template renders). */
      if (window._gmOrdersWired) return;
      var vueEl = document.getElementById("vue");
      var root = vueEl && vueEl._vnode && vueEl._vnode.component;
      if (!root || !root.isMounted) return;
      if (!document.getElementById("gm-admin-root")) return;
      window._gmOrdersWired = true;
      var self = root.proxy;
      self.$watch("gm.merchant", function (m) {
        if (m && self.gm.view === "orders") self.gmLoadOrders();
      });
      self.$watch("gm.view", function (v) {
        if (v === "orders" && self.gm.merchant) self.gmLoadOrders();
      });
    }
  });
})();
