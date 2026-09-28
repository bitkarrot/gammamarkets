/* public_order.js — A3 order status page (§5.4/§11.4 contract).

   The bearer token arrives ONLY as /infinitemarkets/order#<token>. It was
   read + stripped by public_storefront.js (history.replaceState) before
   this module runs and lives in memory only — every request sends it as
   X-Order-Token; it never appears in path, query, or emitted links.
   Renders ONLY the §5.4 field set with buyer-facing labels. */
(function () {
  "use strict";

  var GM = window.GM;
  var root = document.getElementById("gm-order");
  if (!root || !GM) return;

  var STATUS_API = "/infinitemarkets/api/v1/public/order-status";
  var OPTOUT_API = "/infinitemarkets/api/v1/public/order-email-opt-out";
  var POLL_MS = 5000;
  var token = GM.orderToken();

  var statusEl = document.getElementById("gm-order-state");
  var checkingEl = document.getElementById("gm-order-checking");
  var detailEl = document.getElementById("gm-order-detail");
  var invoiceEl = document.getElementById("gm-order-invoice");
  var itemsEl = document.getElementById("gm-order-items");
  var optOutBtn = document.getElementById("gm-opt-out");
  var copyBtn = document.getElementById("gm-copy-status-link");
  var refEl = document.getElementById("gm-order-ref");
  var countdownTimer = null;
  var cardEl = document.getElementById("gm-order-card");
  var promptEl = document.getElementById("gm-order-prompt");
  var titleEl = root.querySelector(".order-title");
  var deliveryEl = document.getElementById("gm-order-delivery");

  /* "Track order" entry: paste a private order link (or just its token).
     The token only ever travels in the URL fragment, which the browser
     never sends to the server; the reload lets the shared module strip it
     into memory as usual. */
  var trackForm = document.getElementById("gm-track-form");
  if (trackForm) {
    trackForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var input = trackForm.querySelector("input[name=order_link]");
      var err = trackForm.querySelector('[data-error-for="order_link"]');
      var raw = (input && input.value || "").trim();
      var hash = raw.indexOf("#");
      var candidate = hash >= 0 ? raw.slice(hash + 1) : raw;
      if (!/^[A-Za-z0-9_-]{43}$/.test(candidate)) {
        if (err) {
          err.textContent = "That doesn't look like an order link. Paste the full link you received after checkout.";
          err.hidden = false;
        }
        return;
      }
      location.hash = candidate;
      location.reload();
    });
  }

  if (!token) {
    /* No fragment: this is the Track-order page, not a dead link — the
       invalid-token copy is reserved for links that were shared. */
    if (statusEl) statusEl.textContent = "";
    if (cardEl) cardEl.hidden = true;
    if (titleEl) titleEl.textContent = "Track your order";
    if (promptEl) promptEl.hidden = false;
    return;
  }
  if (promptEl) promptEl.hidden = true;

  function setChecking(on) {
    /* Loading = last-known content + "checking…" — never spinner-only. */
    if (checkingEl) checkingEl.hidden = !on;
  }

  function renderInvalid() {
    /* Identical copy for dead/rotated/wrong/nonexistent tokens — no
       existence oracle (§11.4). The recovery help stays reachable. */
    if (statusEl) {
      statusEl.textContent = "This order link is no longer valid.";
      statusEl.setAttribute("data-state", "invalid");
    }
    if (detailEl) GM.clear(detailEl);
    if (invoiceEl) invoiceEl.hidden = true;
    if (optOutBtn) optOutBtn.hidden = true;
    if (copyBtn) copyBtn.hidden = true;
    GM.renderDelivery(deliveryEl, []);
    if (promptEl) promptEl.hidden = false;
  }

  function labelFor(body) {
    if (body.payment_exception || body.payment_status === "creation_unknown") {
      return "On hold — the merchant is reviewing a payment issue.";
    }
    return GM.STATE_LABELS[body.state] || "Checking order status…";
  }

  function render(body) {
    if (promptEl) promptEl.hidden = true;
    if (statusEl) {
      statusEl.textContent = labelFor(body);
      var held = body.payment_exception || body.payment_status === "creation_unknown";
      statusEl.setAttribute("data-state", held ? "on_hold" : (body.state || ""));
    }
    if (refEl && body.total_sat !== undefined) {
      refEl.textContent = GM.sats(body.total_sat);
    }
    if (detailEl) {
      GM.clear(detailEl);
      if (body.shipping_state && body.shipping_state !== "not_required") {
        detailEl.appendChild(
          GM.h("p", {
            class: "order-shipping",
            text: "Delivery: " + (GM.SHIPPING_LABELS[body.shipping_state] || body.shipping_state)
          })
        );
      }
    }
    GM.renderDelivery(deliveryEl, body.digital_delivery);
    if (itemsEl) {
      GM.clear(itemsEl);
      (body.items || []).forEach(function (i) {
        itemsEl.appendChild(
          GM.h("li", {
            text:
              i.title + " ×" + i.quantity + " — " + GM.sats(i.line_total_sat)
          })
        );
      });
    }
    if (invoiceEl) {
      if (body.state === "awaiting_payment" && body.bolt11) {
        invoiceEl.hidden = false;
        GM.clear(invoiceEl);
        var qr = GM.h("div", { class: "invoice-qr" });
        invoiceEl.appendChild(qr);
        var ta = GM.h("textarea", {
          class: "bolt11",
          readonly: "",
          "aria-label": "Lightning invoice"
        });
        ta.value = body.bolt11;
        invoiceEl.appendChild(ta);
        var copy = GM.h("button", {
          type: "button",
          class: "btn-secondary",
          text: "Copy invoice"
        });
        copy.addEventListener("click", function () {
          if (navigator.clipboard) {
            navigator.clipboard.writeText(body.bolt11);
            copy.textContent = "Copied";
          }
        });
        invoiceEl.appendChild(copy);
        var cd = GM.h("p", {
          class: "invoice-countdown",
          "aria-live": "polite"
        });
        invoiceEl.appendChild(cd);
        invoiceEl.appendChild(
          GM.h("p", {
            class: "invoice-security",
            text:
              "Invoice is correlated to this order only. Creating it" +
              " does not mark the order paid."
          })
        );
        GM.renderQr(qr, "lightning:" + body.bolt11);
        if (countdownTimer) clearInterval(countdownTimer);
        countdownTimer = setInterval(function () {
          var left = Math.max(0, Number(body.expires_at || 0) - Date.now() / 1000);
          var m = Math.floor(left / 60);
          var s = Math.floor(left % 60);
          cd.textContent = "Expires in " + m + ":" + (s < 10 ? "0" : "") + s;
          if (left <= 0) clearInterval(countdownTimer);
        }, 1000);
      } else {
        invoiceEl.hidden = true;
      }
    }
    if (optOutBtn) {
      optOutBtn.hidden = !body.email_opt_in;
    }
    if (copyBtn) copyBtn.hidden = false;
  }

  var stopped = false;
  function poll() {
    if (stopped) return;
    setChecking(true);
    GM.api(STATUS_API, { headers: { "X-Order-Token": token } })
      .then(function (r) {
        setChecking(false);
        if (r.status === 200) {
          render(r.body);
          if (!GM.isTerminal(r.body.state)) {
            setTimeout(poll, POLL_MS);
          }
        } else if (r.status === 401 || r.status === 404) {
          stopped = true;
          renderInvalid();
        } else {
          setTimeout(poll, POLL_MS);
        }
      })
      .catch(function () {
        setChecking(false);
        setTimeout(poll, POLL_MS);
      });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(GM.statusUrl());
        copyBtn.textContent = "Copied";
      }
    });
  }
  if (optOutBtn) {
    optOutBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      GM.api(OPTOUT_API, {
        method: "POST",
        headers: { "X-Order-Token": token }
      }).then(function () {
        optOutBtn.textContent = "Order emails stopped.";
        optOutBtn.disabled = true;
      });
    });
  }

  poll();
})();
