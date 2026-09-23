/* public_storefront.js — shared helpers for standalone public docs.
   Vanilla JS only: CSP is script-src 'self', no third-party scripts.
   Everything lives under window.GM; page modules are public_checkout.js
   (product card) and public_order.js (status page). */
(function () {
  "use strict";

  var GM = (window.GM = window.GM || {});

  /* --- DOM helpers (never innerHTML with API values — XSS boundary) ---- */

  GM.h = function (tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "text") el.textContent = attrs[k];
        else if (k === "class") el.className = attrs[k];
        else if (k === "hidden" && attrs[k]) el.hidden = true;
        else if (k.slice(0, 5) === "data-" || k === "role" ||
                 k === "aria-live" || k === "aria-label" || k === "type" ||
                 k === "href" || k === "readonly" || k === "id" ||
                 k === "colspan" || k === "for") {
          el.setAttribute(k, attrs[k]);
        }
      });
    }
    (children || []).forEach(function (c) {
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return el;
  };

  GM.clear = function (el) {
    while (el && el.firstChild) el.removeChild(el.firstChild);
  };

  /* --- formatters ------------------------------------------------------- */

  GM.sats = function (n) {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("en-US") + " sats";
  };

  /* Middle-truncate a long reference (order ref, npub) for display. */
  GM.trunc = function (s, head, tail) {
    s = String(s || "");
    head = head || 8;
    tail = tail || 6;
    if (s.length <= head + tail + 3) return s;
    return s.slice(0, head) + "…" + s.slice(-tail);
  };

  /* --- fetch wrapper ----------------------------------------------------- */

  GM.api = function (url, opts) {
    opts = opts || {};
    return fetch(url, {
      method: opts.method || "GET",
      headers: opts.headers || {},
      body: opts.body,
      credentials: "same-origin"
    }).then(function (resp) {
      return resp
        .json()
        .catch(function () {
          return {};
        })
        .then(function (body) {
          return { status: resp.status, body: body };
        });
    });
  };

  /* --- §5.4 token contract -------------------------------------------------
     The bearer token arrives ONLY as a URL fragment. Read it once, strip
     it via history.replaceState, keep it in memory, send it as
     X-Order-Token — never in path/query/links (§5.4/§11.4). */

  var _token = null;
  if (location.hash.length > 1) {
    _token = location.hash.slice(1);
    history.replaceState(null, "", location.pathname);
  }
  GM.orderToken = function () {
    return _token;
  };
  /* The checkout module hands over a freshly issued token (from the 201
     response) — still memory-only, never written to storage or URLs. */
  GM.setOrderToken = function (t) {
    _token = t;
  };
  GM.statusUrl = function () {
    /* The shareable status link carries the token in its fragment — the
       fragment is never sent to the server by any browser. */
    return _token
      ? location.origin + "/gammamarkets/order#" + _token
      : location.origin + "/gammamarkets/order";
  };

  /* --- buyer-facing labels + RFC 9457 -> friendly copy (copywriting
         contract — verbatim strings) ------------------------------------- */

  GM.STATE_LABELS = {
    received: "Order received",
    invoice_pending: "Creating invoice",
    awaiting_payment: "Waiting for payment",
    confirmed: "Payment confirmed",
    processing: "Preparing your order",
    completed: "Complete",
    cancelled: "This order is no longer active",
    rejected: "This order is no longer active",
    expired: "This order is no longer active"
  };

  GM.ERROR_COPY = {
    "insufficient-stock":
      "Not enough stock available — reduce quantity or choose another item.",
    "order-expired":
      "Invoice expired — no payment was taken. Inventory will be released" +
      " safely; create a new invoice only after status reconciliation" +
      " finishes.",
    "rate-limited": "Too many requests — wait a minute and try again.",
    "invalid-shipping-destination":
      "This item cannot be shipped to the selected destination."
  };

  GM.problemCopy = function (body) {
    /* body is an RFC 9457 problem document (urn:gammamarkets:<code>). */
    var code = "";
    if (body && typeof body.type === "string") {
      code = body.type.replace("urn:gammamarkets:", "");
    }
    return (
      GM.ERROR_COPY[code] ||
      (body && (body.detail || body.title)) ||
      "Checkout could not be started."
    );
  };

  /* Terminal order states — polling stops here (§5.4). */
  GM.TERMINAL = {
    confirmed: false, // confirmed still allows forward progress display
    processing: false,
    completed: true,
    cancelled: true,
    rejected: true,
    expired: true
  };
  GM.isTerminal = function (state) {
    return GM.TERMINAL[state] === true;
  };

  /* ISO 3166-1 alpha-2 country list for the checkout country select. */
  GM.COUNTRIES = [
    ["US", "United States"], ["CA", "Canada"], ["MX", "Mexico"],
    ["BR", "Brazil"], ["AR", "Argentina"], ["CL", "Chile"], ["CO", "Colombia"],
    ["GB", "United Kingdom"], ["IE", "Ireland"], ["FR", "France"],
    ["DE", "Germany"], ["NL", "Netherlands"], ["BE", "Belgium"],
    ["ES", "Spain"], ["PT", "Portugal"], ["IT", "Italy"], ["AT", "Austria"],
    ["CH", "Switzerland"], ["SE", "Sweden"], ["NO", "Norway"],
    ["DK", "Denmark"], ["FI", "Finland"], ["PL", "Poland"], ["CZ", "Czechia"],
    ["GR", "Greece"], ["HU", "Hungary"], ["RO", "Romania"],
    ["UA", "Ukraine"], ["TR", "Türkiye"], ["IL", "Israel"],
    ["AU", "Australia"], ["NZ", "New Zealand"], ["JP", "Japan"],
    ["KR", "South Korea"], ["SG", "Singapore"], ["HK", "Hong Kong"],
    ["TW", "Taiwan"], ["IN", "India"], ["TH", "Thailand"], ["VN", "Vietnam"],
    ["PH", "Philippines"], ["ID", "Indonesia"], ["MY", "Malaysia"],
    ["ZA", "South Africa"], ["NG", "Nigeria"], ["KE", "Kenya"],
    ["EG", "Egypt"], ["MA", "Morocco"], ["AE", "United Arab Emirates"],
    ["SA", "Saudi Arabia"], ["IS", "Iceland"], ["LU", "Luxembourg"],
    ["EE", "Estonia"], ["LV", "Latvia"], ["LT", "Lithuania"],
    ["SK", "Slovakia"], ["SI", "Slovenia"], ["HR", "Croatia"],
    ["BG", "Bulgaria"], ["PE", "Peru"], ["UY", "Uruguay"], ["CR", "Costa Rica"],
    ["PA", "Panama"], ["DO", "Dominican Republic"], ["EC", "Ecuador"]
  ];

  /* Gallery thumbs swap the main product image (sketch 001 editorial
     gallery). Delegated listener — no inline handlers, CSP-safe. */
  document.addEventListener("click", function (ev) {
    var thumb =
      ev.target && ev.target.closest
        ? ev.target.closest(".thumb[data-gallery-src]")
        : null;
    if (!thumb) return;
    var main = document.getElementById("gm-gallery-main");
    if (main) main.src = thumb.getAttribute("data-gallery-src");
    document.querySelectorAll(".thumb").forEach(function (el) {
      el.classList.remove("active");
    });
    thumb.classList.add("active");
  });

  /* Render a Lightning invoice QR into el using the host-vendored
     vue-qrcode build (same-origin vendor script — no third-party code).
     Vue.render mounts a standalone vnode; no app instance needed. */
  GM.renderQr = function (el, value) {
    if (!window.Vue || !window.QrcodeVue || !el) return;
    var comp = window.QrcodeVue.default || window.QrcodeVue;
    window.Vue.render(
      window.Vue.h(comp, {
        value: value,
        size: 216,
        level: "M",
        renderAs: "svg",
        margin: 2
      }),
      el
    );
  };
})();
