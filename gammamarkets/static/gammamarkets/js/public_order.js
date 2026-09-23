/* public_order.js — A3 order status page (§5.4/§11.4 contract).

   The bearer token arrives ONLY as /gammamarkets/order#<token>. It was
   read + stripped by public_storefront.js (history.replaceState) before
   this module runs and lives in memory only — every request sends it as
   X-Order-Token; it never appears in path, query, or emitted links.
   Renders ONLY the §5.4 field set with buyer-facing labels. */
(function () {
  "use strict";

  var GM = window.GM;
  var root = document.getElementById("gm-order");
  if (!root || !GM) return;

  var STATUS_API = "/gammamarkets/api/v1/public/order-status";
  var OPTOUT_API = "/gammamarkets/api/v1/public/order-email-opt-out";
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

  if (!token) {
    /* No fragment at all — same copy as a dead token would produce is
       NOT used here (nothing was ever shared); the prompt explains the
       page expects an order link. */
    if (statusEl) statusEl.textContent = "";
    var prompt = document.getElementById("gm-order-prompt");
    if (prompt) prompt.hidden = false;
    return;
  }

  function setChecking(on) {
    /* Loading = last-known content + "checking…" — never spinner-only. */
    if (checkingEl) checkingEl.hidden = !on;
  }

  function renderInvalid() {
    /* Identical copy for dead/rotated/wrong/nonexistent tokens — no
       existence oracle (§11.4). */
    if (statusEl)
      statusEl.textContent = "This order link is no longer valid.";
    if (detailEl) GM.clear(detailEl);
    if (invoiceEl) invoiceEl.hidden = true;
    if (optOutBtn) optOutBtn.hidden = true;
    if (copyBtn) copyBtn.hidden = true;
    var prompt = document.getElementById("gm-order-prompt");
    if (prompt) prompt.hidden = true;
  }

  function labelFor(body) {
    if (body.payment_exception || body.payment_status === "creation_unknown") {
      return "On hold — the merchant is reviewing a payment issue.";
    }
    return GM.STATE_LABELS[body.state] || "Checking order status…";
  }

  function render(body) {
    var prompt = document.getElementById("gm-order-prompt");
    if (prompt) prompt.hidden = true;
    if (statusEl) {
      statusEl.textContent = labelFor(body);
      statusEl.setAttribute("data-state", body.state || "");
    }
    if (refEl && body.total_sat !== undefined) {
      refEl.textContent = GM.sats(body.total_sat);
    }
    if (detailEl) {
      GM.clear(detailEl);
      if (body.shipping_state) {
        detailEl.appendChild(
          GM.h("p", {
            class: "order-shipping",
            text: "Shipping: " + body.shipping_state
          })
        );
      }
    }
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
