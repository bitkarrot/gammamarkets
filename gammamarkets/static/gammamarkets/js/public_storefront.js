/* public_storefront.js — buyer-side behaviors for standalone public docs.
   Vanilla JS only: CSP is script-src 'self', no third-party scripts. */
(function () {
  "use strict";

  /* A3: the bearer token lives only in the URL fragment — strip it
     immediately and keep it in memory (spec section 5.4/11.4). */
  var orderToken = null;
  if (location.hash.length > 1) {
    orderToken = location.hash.slice(1);
    history.replaceState(null, "", location.pathname);
  }

  /* A1: variation selector — an unchosen or disabled combination blocks
     submit with the inline error (never a silent dead button). */
  var form = document.getElementById("gm-checkout");
  if (form) {
    var variations = document.querySelectorAll(
      "#gm-variations input[name=variation]"
    );
    var errorEl = form.querySelector(".form-error");
    var varError = document.querySelector(".variation-error");

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (errorEl) errorEl.hidden = true;
      if (varError) varError.hidden = true;

      var dTag = form.dataset.dTag;
      if (variations.length) {
        var chosen = document.querySelector(
          "#gm-variations input[name=variation]:checked"
        );
        if (!chosen) {
          if (varError) varError.hidden = false;
          return;
        }
        dTag = chosen.value;
      }

      var qty = parseInt(
        (form.querySelector("input[name=quantity]") || {}).value || "1",
        10
      );
      if (!(qty >= 1 && qty <= 10000)) {
        if (errorEl) {
          errorEl.textContent = "Enter a valid quantity.";
          errorEl.hidden = false;
        }
        return;
      }

      /* Idempotency-Key: generated once per page load, [A-Za-z0-9_-]{32,128}
         from >=128 random bits (spec section 5.4). */
      if (!form.dataset.idem) {
        var buf = new Uint8Array(32);
        crypto.getRandomValues(buf);
        form.dataset.idem = btoa(String.fromCharCode.apply(null, buf))
          .replace(/\+/g, "-")
          .replace(/\//g, "_")
          .replace(/=+$/, "");
      }

      var email = (
        (form.querySelector("input[name=email]") || {}).value || ""
      ).trim();
      var payload = {
        merchant_pubkey: form.dataset.merchant,
        items: [{ d_tag: dTag, quantity: qty }]
      };
      if (email) payload.contact = { email: email };

      var btn = form.querySelector("button[type=submit]");
      if (btn) btn.disabled = true;
      fetch(form.dataset.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": form.dataset.idem
        },
        body: JSON.stringify(payload)
      })
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { status: resp.status, body: body };
          });
        })
        .then(function (r) {
          if (r.status === 201 && r.body.public_token) {
            location.href =
              "/gammamarkets/order#" + r.body.public_token;
            return;
          }
          if (errorEl) {
            errorEl.textContent =
              (r.body && (r.body.detail || r.body.title)) ||
              "Checkout could not be started.";
            errorEl.hidden = false;
          }
          if (btn) btn.disabled = false;
        })
        .catch(function () {
          if (errorEl) {
            errorEl.textContent = "Network error — try again.";
            errorEl.hidden = false;
          }
          if (btn) btn.disabled = false;
        });
    });
  }

  /* A3: order-status page — the token (already stripped from the URL)
     travels only as X-Order-Token; the status poll renders state and
     the invoice while awaiting payment. */
  var statusEl = document.getElementById("gm-order");
  if (statusEl && orderToken) {
    var render = function (body) {
      var html =
        "<h1>Order " + body.state + "</h1>" +
        "<p class=\"order-total\">" + body.total_sat + " sats</p>";
      if (body.shipping_state) {
        html += "<p class=\"order-shipping\">Shipping: " +
          body.shipping_state + "</p>";
      }
      if (body.items && body.items.length) {
        html += "<ul class=\"order-items\">";
        body.items.forEach(function (item) {
          html += "<li>" + item.title + " x" + item.quantity + "</li>";
        });
        html += "</ul>";
      }
      if (body.state === "awaiting_payment" && body.bolt11) {
        html +=
          "<p class=\"invoice-prompt\">Pay this Lightning invoice:</p>" +
          "<textarea class=\"bolt11\" readonly>" + body.bolt11 +
          "</textarea>";
        if (body.invoice_expiry) {
          html += "<p class=\"invoice-expiry\">Expires: " +
            new Date(body.invoice_expiry * 1000).toLocaleString() +
            "</p>";
        }
      }
      if (body.payment_exception) {
        html += "<p class=\"order-notice\">This order needs merchant" +
          " attention — contact the store.</p>";
      }
      html += "<p class=\"opt-out\"><a href=\"#\" id=\"gm-opt-out\">" +
        "Stop email notifications</a></p>";
      statusEl.innerHTML = html;
      var optOut = document.getElementById("gm-opt-out");
      if (optOut) {
        optOut.addEventListener("click", function (ev) {
          ev.preventDefault();
          fetch("/gammamarkets/api/v1/public/order-email-opt-out", {
            method: "POST",
            headers: { "X-Order-Token": orderToken }
          });
          optOut.textContent = "Email notifications stopped.";
        });
      }
    };
    var poll = function () {
      fetch("/gammamarkets/api/v1/public/order-status", {
        headers: { "X-Order-Token": orderToken }
      })
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { status: resp.status, body: body };
          });
        })
        .then(function (r) {
          if (r.status === 200) {
            render(r.body);
            if (r.body.state === "awaiting_payment") {
              setTimeout(poll, 4000);
            }
          } else {
            statusEl.innerHTML =
              "<p class=\"order-prompt\">Order link is not valid.</p>";
          }
        })
        .catch(function () {
          setTimeout(poll, 8000);
        });
    };
    poll();
  } else if (statusEl) {
    statusEl.innerHTML =
      "<h1>Order status</h1>" +
      "<p class=\"order-prompt\">Open your order link to view its" +
      " status.</p>";
  }
})();
