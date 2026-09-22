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

      var btn = form.querySelector("button[type=submit]");
      if (btn) btn.disabled = true;
      fetch(form.dataset.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": form.dataset.idem
        },
        body: JSON.stringify({
          merchant_pubkey: form.dataset.merchant,
          items: [{ d_tag: dTag, quantity: qty }]
        })
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
})();
