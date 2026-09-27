/* public_checkout.js — A2 adaptive checkout (sketch 001-D Adaptive Blend).

   The checkout card is embedded in the A1 product document (there is no
   standalone checkout route in §5.4). Layout presets are merchant-chosen
   (editorial | guided | compact via data-layout); ≤560px forces compact.
   The field set, summary, validation, payment states, and security copy
   are invariant across presets and themes. */
(function () {
  "use strict";

  var GM = window.GM;
  var form = document.getElementById("gm-checkout");
  var card = document.getElementById("gm-checkout-card");
  if (!form || !card || !GM) return;

  var STATUS_API = "/gammamarkets/api/v1/public/order-status";

  /* --- layout ------------------------------------------------------------
     Merchant preset drives desktop presentation; ≤560px always compacts
     (responsive safety overrides the preference — never a squeezed
     desktop layout on mobile). */
  var mqNarrow = window.matchMedia
    ? window.matchMedia("(max-width: 560px)")
    : { matches: false };
  function effectiveLayout() {
    var preset = card.getAttribute("data-layout") || "editorial";
    return mqNarrow.matches ? "compact" : preset;
  }

  /* --- guided stepper (Product → Delivery → Pay) ------------------------- */
  var step = 1;
  var lastMode = null;

  function syncVisibility() {
    var mode = effectiveLayout();
    card.querySelectorAll(".co-section").forEach(function (sec) {
      var body = sec.querySelector(".co-section-body");
      var n = Number(sec.getAttribute("data-step") || "0");
      if (!body) return;
      if (mode === "guided") {
        /* Sketch 001-B: exactly one step panel at a time — step 3 (Pay)
           shows only the persistent summary + submit. */
        body.hidden = n !== step;
      } else if (mode === "compact") {
        body.hidden = sec.getAttribute("data-open") !== "true";
      } else {
        body.hidden = false;
      }
    });
    var payBack = card.querySelector("[data-pay-back]");
    if (payBack) payBack.hidden = !(mode === "guided" && step === 3);
    card.querySelectorAll(".progress-step").forEach(function (el) {
      el.classList.toggle(
        "active",
        Number(el.getAttribute("data-step")) === step
      );
      el.classList.toggle(
        "done",
        Number(el.getAttribute("data-step")) < step
      );
    });
  }

  function applyLayout() {
    var mode = effectiveLayout();
    card.setAttribute("data-mode", mode);
    /* The preset recomposes the WHOLE page shell, not just the card —
       guided = focused step flow, compact = narrow express sheet
       (sketch 001-B/C). */
    var layout = card.closest(".product-layout");
    if (layout) layout.setAttribute("data-mode", mode);
    var progress = card.querySelector(".progress");
    if (progress) progress.hidden = mode !== "guided";
    card.querySelectorAll(".co-section").forEach(function (sec) {
      var head = sec.querySelector(".co-section-head");
      if (head) head.hidden = mode !== "compact";
    });
    if (mode !== lastMode) {
      if (mode === "compact") {
        /* Progressive disclosure (sketch 001-C): the first section open,
           later ones collapsed behind their disclosure heads. */
        var first = true;
        card.querySelectorAll(".co-section").forEach(function (sec) {
          sec.setAttribute("data-open", first ? "true" : "false");
          var head = sec.querySelector(".co-section-head");
          if (head) {
            head.setAttribute(
              "aria-expanded", first ? "true" : "false"
            );
          }
          first = false;
        });
      }
      if (mode === "guided") step = 1;
      lastMode = mode;
    }
    syncVisibility();
  }
  if (mqNarrow.addEventListener) {
    mqNarrow.addEventListener("change", applyLayout);
  }

  /* Compact disclosure: section heads toggle their bodies open. */
  card.querySelectorAll(".co-section-head").forEach(function (head) {
    head.addEventListener("click", function () {
      var sec = head.parentElement;
      var open = sec.getAttribute("data-open") === "true";
      sec.setAttribute("data-open", open ? "false" : "true");
      head.setAttribute("aria-expanded", open ? "false" : "true");
      syncVisibility();
    });
  });

  /* --- country select ----------------------------------------------------- */
  var countrySel = form.querySelector("select[name=country]");
  if (countrySel && countrySel.options.length <= 1) {
    GM.COUNTRIES.forEach(function (c) {
      countrySel.appendChild(GM.h("option", { text: c[1] }));
      countrySel.lastChild.value = c[0];
    });
  }

  /* --- inline validation (aria-live, contract copy) ---------------------- */
  function fieldError(name, msg) {
    var err = form.querySelector('[data-error-for="' + name + '"]');
    if (!err) return;
    if (msg) {
      err.textContent = msg;
      err.hidden = false;
    } else {
      err.textContent = "";
      err.hidden = true;
    }
  }

  /* --- order summary (persistent Items/Shipping/Total) ------------------- */
  var summaryItems = card.querySelector('[data-sum="items"]');
  var summaryShipping = card.querySelector('[data-sum="shipping"]');
  var summaryTotal = card.querySelector('[data-sum="total"]');
  var refreshQuote = card.querySelector("[data-refresh-quote]");
  var quote = null;
  var quoteVersion = 0;
  var quoteTimer = null;
  var lastQuotePayload = null;
  var QUOTE_API = "/gammamarkets/api/v1/public/quote";

  function currentQty() {
    var q = Number((form.querySelector("input[name=quantity]") || {}).value || "0");
    return Number.isInteger(q) ? q : 0;
  }
  function quotePayload() {
    var chosen = form.querySelector("input[name=variation]:checked");
    if (form.querySelectorAll("input[name=variation]").length && !chosen) return null;
    var qty = currentQty();
    if (qty < 1 || qty > 10000) return null;
    var payload = {
      merchant_pubkey: form.getAttribute("data-merchant"),
      items: [{d_tag: chosen ? chosen.value : form.getAttribute("data-d-tag"), quantity: qty}]
    };
    if (form.getAttribute("data-physical") === "true") {
      var country = countrySel ? countrySel.value : "";
      var shipping = form.querySelector("select[name=shipping_option]");
      if (!country || !shipping || !shipping.value) return null;
      payload.shipping_option_d = shipping.value;
      payload.address = {country: country, region: val("region")};
    }
    return payload;
  }
  function updateSummary(ev) {
    if (ev && ["quantity", "variation", "country", "region", "shipping_option"]
        .indexOf(ev.target.name) < 0) return;
    if (pendingPayload) return;
    var payload = quotePayload();
    var signature = payload ? JSON.stringify(payload) : null;
    if (ev && signature === lastQuotePayload) return;
    lastQuotePayload = signature;
    var version = ++quoteVersion;
    clearTimeout(quoteTimer);
    quote = null;
    if (refreshQuote) refreshQuote.hidden = true;
    if (submitButton) submitButton.disabled = true;
    if (summaryItems) summaryItems.textContent = "—";
    if (summaryShipping) summaryShipping.textContent =
      form.getAttribute("data-physical") === "true" ? "Choose delivery" : "0 sats";
    if (summaryTotal) summaryTotal.textContent = "—";
    if (!payload) {
      if (submitButton) submitButton.disabled = false;
      return;
    }
    quoteTimer = setTimeout(function () {
      GM.api(QUOTE_API, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (version !== quoteVersion || pendingPayload) return;
        if (r.status !== 200 || !Number.isSafeInteger(r.body.total_sat)) {
          if (summaryTotal) summaryTotal.textContent = GM.problemCopy(r.body);
          if (refreshQuote) refreshQuote.hidden = false;
          return;
        }
        quote = r.body;
        if (summaryItems) summaryItems.textContent = GM.sats(quote.subtotal_sat);
        if (summaryShipping) summaryShipping.textContent = GM.sats(quote.shipping_sat);
        if (summaryTotal) summaryTotal.textContent = GM.sats(quote.total_sat);
        if (submitButton) submitButton.disabled = false;
      }).catch(function () {
        if (version === quoteVersion && summaryTotal) {
          summaryTotal.textContent = "Price unavailable — try again shortly.";
          if (refreshQuote) refreshQuote.hidden = false;
        }
      });
    }, 120);
  }
  if (refreshQuote) refreshQuote.addEventListener("click", function () { updateSummary(); });
  form.addEventListener("change", updateSummary);
  form.addEventListener("input", updateSummary);

  /* --- invoice state machine ----------------------------------------------
     creating (skeleton, no QR) → awaiting_payment → confirmed |
     expired | creation_unknown | cancelled — never a second invoice
     after uncertainty (§8.2). */
  var panel = document.getElementById("gm-invoice-panel");
  var pollTimer = null;
  var token = null; // in-memory only — never in path/query/links
  var countdownTimer = null;

  function pill(label, kind) {
    return GM.h("span", { class: "pill pill-" + kind, text: label });
  }

  function renderCreating() {
    if (!panel) return;
    GM.clear(panel);
    panel.hidden = false;
    panel.setAttribute("data-invoice-state", "creating");
    panel.appendChild(
      GM.h("div", { class: "invoice-skeleton", "aria-live": "polite" }, [
        GM.h("div", { class: "skel skel-qr" }),
        GM.h("div", { class: "skel skel-line" }),
        GM.h("div", { class: "skel skel-line short" }),
        GM.h("p", { class: "invoice-note", text: "Creating your invoice…" })
      ])
    );
  }

  function renderAwaiting(bolt11, expiresAt, totalSat) {
    if (!panel) return;
    GM.clear(panel);
    panel.hidden = false;
    panel.setAttribute("data-invoice-state", "awaiting_payment");
    var wrap = GM.h("div", { class: "invoice-view" });
    wrap.appendChild(pill("Waiting for payment", "waiting"));
    var qr = GM.h("div", { class: "invoice-qr" });
    wrap.appendChild(qr);
    if (totalSat !== null && totalSat !== undefined) {
      wrap.appendChild(
        GM.h("p", { class: "invoice-amount", text: GM.sats(totalSat) })
      );
    }
    var countdown = GM.h("p", {
      class: "invoice-countdown",
      "aria-live": "polite"
    });
    wrap.appendChild(countdown);
    var ta = GM.h("textarea", {
      class: "bolt11",
      readonly: "",
      "aria-label": "Lightning invoice"
    });
    ta.value = bolt11 || "";
    wrap.appendChild(ta);
    var copyBtn = GM.h("button", {
      type: "button",
      class: "btn-secondary",
      text: "Copy invoice"
    });
    copyBtn.addEventListener("click", function () {
      if (navigator.clipboard && bolt11) {
        navigator.clipboard.writeText(bolt11);
        copyBtn.textContent = "Copied";
      }
    });
    wrap.appendChild(copyBtn);
    var linkBtn = GM.h("button", {
      type: "button",
      class: "btn-secondary",
      text: "Copy status link"
    });
    linkBtn.addEventListener("click", function () {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(GM.statusUrl());
        linkBtn.textContent = "Copied";
      }
    });
    wrap.appendChild(linkBtn);
    wrap.appendChild(
      GM.h("p", {
        class: "invoice-security",
        text:
          "Invoice is correlated to this order only. Creating it does" +
          " not mark the order paid."
      })
    );
    panel.appendChild(wrap);
    GM.renderQr(qr, "lightning:" + (bolt11 || ""));
    startCountdown(countdown, expiresAt);
  }

  function startCountdown(el, expiresAt) {
    if (countdownTimer) clearInterval(countdownTimer);
    function tick() {
      var left = Math.max(0, Number(expiresAt || 0) - Date.now() / 1000);
      var m = Math.floor(left / 60);
      var s = Math.floor(left % 60);
      el.textContent =
        "Expires in " + m + ":" + (s < 10 ? "0" : "") + s;
      if (left <= 0 && countdownTimer) {
        clearInterval(countdownTimer);
        countdownTimer = null;
      }
    }
    tick();
    countdownTimer = setInterval(tick, 1000);
  }

  function renderConfirmed(body) {
    if (!panel) return;
    GM.clear(panel);
    panel.hidden = false;
    panel.setAttribute("data-invoice-state", "confirmed");
    var wrap = GM.h("div", { class: "invoice-view" });
    wrap.appendChild(
      pill(
        GM.STATE_LABELS[body.state] || "Payment confirmed",
        "success"
      )
    );
    wrap.appendChild(
      GM.h("p", {
        class: "invoice-amount",
        text: GM.sats(body.total_sat)
      })
    );
    if (body.items && body.items.length) {
      var ul = GM.h("ul", { class: "order-items" });
      body.items.forEach(function (i) {
        ul.appendChild(
          GM.h("li", {
            text: i.title + " ×" + i.quantity + " — " +
              GM.sats(i.line_total_sat)
          })
        );
      });
      wrap.appendChild(ul);
    }
    var linkBtn = GM.h("button", {
      type: "button",
      class: "btn-secondary",
      text: "Copy status link"
    });
    linkBtn.addEventListener("click", function () {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(GM.statusUrl());
        linkBtn.textContent = "Copied";
      }
    });
    wrap.appendChild(linkBtn);
    panel.appendChild(wrap);
  }

  function renderExpired() {
    if (!panel) return;
    GM.clear(panel);
    panel.hidden = false;
    panel.setAttribute("data-invoice-state", "expired");
    var wrap = GM.h("div", { class: "invoice-view" });
    wrap.appendChild(pill("This order is no longer active", "muted"));
    wrap.appendChild(
      GM.h("p", {
        class: "invoice-note",
        text:
          "Invoice expired. If you already paid, do not pay again;" +
          " contact the merchant. Wait for status verification before" +
          " starting a new checkout."
      })
    );
    var review = GM.h("button", {
      type: "button",
      class: "btn-secondary",
      text: "Review order again"
    });
    review.addEventListener("click", function () {
      panel.hidden = true;
      form.hidden = false;
      token = null;
    });
    wrap.appendChild(review);
    panel.appendChild(wrap);
  }

  function renderUncertain() {
    /* §8.2: invoice creation outcome unknown — NEVER offer a second
       invoice or a "pay again" affordance. The status poll is the only
       recovery path. */
    if (!panel) return;
    GM.clear(panel);
    panel.hidden = false;
    panel.setAttribute("data-invoice-state", "creation_unknown");
    var wrap = GM.h("div", { class: "invoice-view" });
    wrap.appendChild(
      pill("On hold — the merchant is reviewing a payment issue.", "warn")
    );
    wrap.appendChild(
      GM.h("p", {
        class: "invoice-note",
        text:
          "Payment status is being verified with the payment provider." +
          " An invoice may already have been created — do not pay a second" +
          " invoice."
      })
    );
    panel.appendChild(wrap);
  }

  function renderCancelled() {
    if (!panel) return;
    GM.clear(panel);
    panel.hidden = false;
    panel.setAttribute("data-invoice-state", "cancelled");
    var wrap = GM.h("div", { class: "invoice-view" });
    wrap.appendChild(pill("This order is no longer active", "muted"));
    panel.appendChild(wrap);
  }

  /* --- status polling (5s, X-Order-Token, stop at terminal) --------------- */
  function pollStatus() {
    if (!token) return;
    GM.api(STATUS_API, { headers: { "X-Order-Token": token } })
      .then(function (r) {
        if (r.status !== 200) return;
        var body = r.body;
        if (body.payment_exception || body.payment_status === "creation_unknown") {
          renderUncertain();
        } else if (body.state === "awaiting_payment" && body.bolt11) {
          renderAwaiting(body.bolt11, body.expires_at, body.total_sat);
        } else if (
          body.state === "confirmed" ||
          body.state === "processing" ||
          body.state === "completed"
        ) {
          renderConfirmed(body);
        } else if (body.state === "expired") {
          renderExpired();
        } else if (body.state === "cancelled" || body.state === "rejected") {
          renderCancelled();
        }
        if (!GM.isTerminal(body.state)) {
          pollTimer = setTimeout(pollStatus, 5000);
        }
      })
      .catch(function () {
        pollTimer = setTimeout(pollStatus, 5000);
      });
  }

  function beginOrder(publicToken, order) {
    token = publicToken; /* memory only — §5.4 */
    GM.setOrderToken(publicToken);
    form.hidden = true;
    if (order && order.state === "awaiting_payment" && order.bolt11) {
      renderAwaiting(order.bolt11, order.expires_at, order.total_sat);
    } else {
      renderCreating();
    }
    pollTimer = setTimeout(pollStatus, 5000);
  }

  /* --- submit --------------------------------------------------------------
     Idempotency-Key: generated once per checkout session from ≥128
     random bits, [A-Za-z0-9_-]{32,128}, REUSED on every retry — a 409
     replay renders the existing order rather than creating a second. */
  var idempotencyKey = null;
  function checkoutKey() {
    if (!idempotencyKey) {
      var buf = new Uint8Array(32); // 256 bits ≥ 128 required
      crypto.getRandomValues(buf);
      idempotencyKey = btoa(String.fromCharCode.apply(null, buf))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
    }
    return idempotencyKey;
  }

  var errorEl = form.querySelector(".form-error");
  var varError = document.querySelector(".variation-error");
  var submitButton = form.querySelector("button[type=submit]");
  var pendingPayload = null;
  var retryUncertain = false;
  var lockedFields = null;
  function lockFields(locked) {
    if (locked && !lockedFields) {
      lockedFields = Array.from(form.querySelectorAll("input, select"))
        .map(function (el) { return {el: el, disabled: el.disabled}; });
      lockedFields.forEach(function (field) { field.el.disabled = true; });
    } else if (!locked && lockedFields) {
      lockedFields.forEach(function (field) { field.el.disabled = field.disabled; });
      lockedFields = null;
    }
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (errorEl) errorEl.hidden = true;
    if (varError) varError.hidden = true;

    var dTag = form.getAttribute("data-d-tag");
    var chosen = form.querySelector("input[name=variation]:checked");
    if (form.querySelectorAll("input[name=variation]").length) {
      if (!chosen) {
        if (varError) varError.hidden = false;
        return;
      }
      dTag = chosen.value;
    }

    var qty = currentQty();
    if (!(qty >= 1 && qty <= 10000)) {
      fieldError("quantity", "Enter a valid quantity.");
      return;
    }

    var physical = form.getAttribute("data-physical") === "true";
    var payload = {
      merchant_pubkey: form.getAttribute("data-merchant"),
      items: [{ d_tag: dTag, quantity: qty }]
    };
    if (physical) {
      var country = countrySel ? countrySel.value : "";
      if (!country) {
        fieldError("country", "Choose a shipping option for this destination.");
        return;
      }
      var shipSel = form.querySelector("select[name=shipping_option]");
      if (!shipSel || !shipSel.value) {
        fieldError(
          "shipping_option",
          "Choose a shipping option for this destination."
        );
        return;
      }
      payload.shipping_option_d = shipSel.value;
      payload.address = {
        country: country,
        region: val("region"),
        line1: val("line1"),
        city: val("city"),
        postal_code: val("postal_code")
      };
    }
    var email = val("email");
    var optIn = form.querySelector("input[name=email_opt_in]");
    var wantsEmail = optIn && optIn.checked;
    if (wantsEmail && !email) {
      /* consent-without-email — contract copy */
      fieldError(
        "email",
        "Enter an email to receive order updates, or turn updates off."
      );
      return;
    }
    if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      fieldError("email", "Enter a valid email for order updates.");
      return;
    }
    if (email) payload.email = email;
    payload.email_opt_in = wantsEmail;

    if (!pendingPayload) {
      if (!quote) {
        if (errorEl) {
          errorEl.textContent = "Wait for the current total before paying.";
          errorEl.hidden = false;
        }
        return;
      }
      payload.expected_total_sat = quote.total_sat;
      pendingPayload = JSON.stringify(payload);
    }
    lockFields(true);
    if (submitButton) submitButton.disabled = true;
    renderCreating();

    GM.api(form.getAttribute("data-endpoint"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": checkoutKey()
      },
      body: pendingPayload
    })
      .then(function (r) {
        /* 201 and 409 replay both carry {public_token, order} — the
           replay renders the existing order, never a duplicate. */
        if (
          (r.status === 201 || r.status === 200) &&
          r.body.public_token
        ) {
          beginOrder(r.body.public_token, r.body.order);
          return;
        }
        if (r.status === 409 && r.body.public_token) {
          beginOrder(r.body.public_token, r.body.order);
          return;
        }
        if (panel) panel.hidden = true;
        form.hidden = false;
        if (r.status === 422 && !retryUncertain) {
          pendingPayload = null;
          idempotencyKey = null;
          lockFields(false);
          updateSummary();
        } else {
          retryUncertain = true;
        }
        if (errorEl) {
          errorEl.textContent = GM.problemCopy(r.body);
          errorEl.hidden = false;
        }
        if (submitButton && pendingPayload) submitButton.disabled = false;
      })
      .catch(function () {
        retryUncertain = true;
        if (panel) panel.hidden = true;
        form.hidden = false;
        if (errorEl) {
          errorEl.textContent = "Network error — retry this same checkout.";
          errorEl.hidden = false;
        }
        if (submitButton) submitButton.disabled = false;
      });
  });

  function val(name) {
    var el = form.querySelector("[name=" + name + "]");
    return el ? el.value.trim() : "";
  }

  /* Guided step CTAs — "Continue to delivery" precedes "Review payment". */
  card.querySelectorAll("[data-goto-step]").forEach(function (btn) {
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      step = Number(btn.getAttribute("data-goto-step"));
      syncVisibility();
    });
  });

  applyLayout();
  updateSummary();
})();
