/* public_nostr.js — NIP-07 buyer sign-in + order history (Release B).

   Flow: "Sign in with Nostr" (rendered only when the shop's inbox is
   active, D-06) -> GET /nostr/challenge -> window.nostr.signEvent
   (kind 22242, challenge in content + tag) -> POST /nostr/verify ->
   HttpOnly session cookie -> GET /nostr/orders renders the buyer's own
   history. The session token never touches JS — the cookie is HttpOnly.
   All DOM builds go through GM.h (no innerHTML with API values). */
(function () {
  "use strict";

  var GM = window.GM || {};
  var API = "/infinitemarkets/api/v1/public";
  var KIND_SIGNIN = 22242;

  var btn = document.getElementById("gm-nostr-signin");
  var panel = document.getElementById("gm-nostr-panel");
  if (!btn || !panel) return;

  var state = { signedIn: false, npub: "", orders: [], busy: false };

  function shopQuery() {
    var root = document.querySelector(".gm-public[data-shop]");
    var shop = root ? root.getAttribute("data-shop") : "";
    return /^[0-9a-f]{64}$/.test(shop || "") ? "?shop=" + shop : "";
  }

  function api(url, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    if (opts.method && opts.method !== "GET") {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
      headers["Origin"] = location.origin;
    }
    return GM.api(API + url, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body
    });
  }

  function note(text, cls) {
    return GM.h("p", { class: "nostr-note " + (cls || ""), text: text });
  }

  function npubShort(npub) {
    return GM.trunc(npub || "", 12, 6);
  }

  /* --- renderers -------------------------------------------------------- */

  function renderSignedOut(msg) {
    GM.clear(panel);
    panel.hidden = false;
    panel.appendChild(
      GM.h("div", { class: "nostr-box", "data-gm": "nostr-signed-out" }, [
        GM.h("p", {
          class: "nostr-lead",
          text: "Sign in with your Nostr key to see all your orders from this shop."
        }),
        note(
          msg ||
            "You need a Nostr signing extension (NIP-07) in this browser —" +
              " for example Alby or nos2x. Nothing is shared with the shop" +
              " beyond a signature that proves your key."
        )
      ])
    );
    btn.textContent = "Sign in with Nostr";
  }

  function renderBusy() {
    GM.clear(panel);
    panel.hidden = false;
    panel.appendChild(
      GM.h("div", { class: "nostr-box" }, [
        note("Waiting for your signer… check the extension prompt.")
      ])
    );
  }

  function orderRow(order) {
    var label = GM.STATE_LABELS[order.state] || order.state || "";
    var row = GM.h("li", { class: "nostr-order", "data-gm": "nostr-order" });
    var head = GM.h("div", { class: "nostr-order-head" }, [
      GM.h("strong", { text: order.first_item || "Order" }),
      GM.h("span", { class: "status-pill", text: label })
    ]);
    row.appendChild(head);
    var meta = [];
    if (order.total_sat !== null && order.total_sat !== undefined) {
      meta.push(GM.sats(order.total_sat));
    }
    if (order.created_at) {
      meta.push(new Date(order.created_at * 1000).toLocaleDateString());
    }
    if (meta.length) {
      row.appendChild(
        GM.h("p", { class: "nostr-order-meta", text: meta.join(" · ") })
      );
    }
    if (order.digital_delivery && order.digital_delivery.length) {
      var delivery = GM.h("div", { class: "nostr-delivery" });
      GM.renderDelivery(delivery, order.digital_delivery);
      row.appendChild(delivery);
    }
    var links = GM.h("div", { class: "nostr-order-links" });
    if (order.status_url) {
      var link = GM.h("a", {
        href: order.status_url,
        text: "View order details",
        class: "nostr-order-link"
      });
      links.appendChild(link);
    }
    if (links.childNodes.length) row.appendChild(links);
    return row;
  }

  function renderSignedIn() {
    GM.clear(panel);
    panel.hidden = false;
    var box = GM.h("div", { class: "nostr-box", "data-gm": "nostr-signed-in" });
    var head = GM.h("div", { class: "nostr-account" }, [
      GM.h("p", {
        class: "nostr-lead",
        text: "Signed in as " + npubShort(state.npub)
      }),
      GM.h("button", {
        type: "button",
        class: "btn-secondary",
        id: "gm-nostr-signout",
        text: "Sign out"
      })
    ]);
    box.appendChild(head);
    box.appendChild(GM.h("h3", { text: "Your orders" }));
    if (!state.orders.length) {
      box.appendChild(
        note("No orders yet — your orders will appear here.")
      );
    } else {
      var list = GM.h("ul", { class: "nostr-orders" });
      state.orders.forEach(function (o) {
        list.appendChild(orderRow(o));
      });
      box.appendChild(list);
    }
    /* Claim: paste a private order link to bind it to this key (D-05). */
    var claimBox = GM.h("div", { class: "nostr-claim" }, [
      GM.h("label", {
        for: "gm-claim-input",
        class: "nostr-claim-label",
        text: "Have a private order link? Paste it to link the order to this key."
      }),
      GM.h("input", {
        type: "text",
        id: "gm-claim-input",
        class: "nostr-claim-input",
        "data-gm": "claim-input",
        "aria-label": "Private order link"
      }),
      GM.h("button", {
        type: "button",
        class: "btn-secondary",
        id: "gm-claim-btn",
        text: "Link this order to my Nostr key"
      }),
      GM.h("p", { class: "nostr-claim-msg", id: "gm-claim-msg" })
    ]);
    box.appendChild(claimBox);
    panel.appendChild(box);
    btn.textContent = "My orders";

    var out = document.getElementById("gm-nostr-signout");
    if (out) out.addEventListener("click", doSignOut);
    var claimBtn = document.getElementById("gm-claim-btn");
    if (claimBtn) claimBtn.addEventListener("click", doClaim);
  }

  /* --- flows ------------------------------------------------------------ */

  function loadOrders() {
    return api("/nostr/orders").then(function (res) {
      if (res.status === 200) {
        state.signedIn = true;
        state.orders = (res.body && res.body.orders) || [];
        renderSignedIn();
        return true;
      }
      state.signedIn = false;
      state.orders = [];
      return false;
    });
  }

  function doSignIn() {
    if (state.busy) return;
    /* Extension-absent is a friendly state, never a crash. */
    if (!window.nostr || typeof window.nostr.signEvent !== "function") {
      renderSignedOut(
        "No Nostr signer found. Install a NIP-07 extension" +
          " (for example Alby or nos2x), then try again."
      );
      return;
    }
    state.busy = true;
    renderBusy();
    api("/nostr/challenge" + shopQuery())
      .then(function (res) {
        if (res.status !== 200 || !res.body.challenge) {
          throw new Error("challenge failed");
        }
        var challenge = res.body.challenge;
        return window.nostr
          .signEvent({
            kind: KIND_SIGNIN,
            created_at: Math.floor(Date.now() / 1000),
            content: challenge,
            tags: [["challenge", challenge]]
          })
          .then(function (signed) {
            return api("/nostr/verify" + shopQuery(), {
              method: "POST",
              body: JSON.stringify({ event: JSON.stringify(signed) })
            });
          });
      })
      .then(function (res) {
        if (!res) return;
        if (res.status === 200) {
          state.npub = (res.body && res.body.pubkey) || "";
          return loadOrders();
        }
        if (res.status !== undefined) {
          renderSignedOut(
            "Sign-in could not be verified. Try again — your signer may" +
              " have declined or the request expired."
          );
        }
      })
      .catch(function () {
        renderSignedOut(
          "Sign-in was cancelled or failed. Try again when you're ready."
        );
      })
      .finally(function () {
        state.busy = false;
      });
  }

  function doSignOut() {
    api("/nostr/logout", { method: "POST" }).finally(function () {
      state.signedIn = false;
      state.npub = "";
      state.orders = [];
      GM.clear(panel);
      panel.hidden = true;
      btn.textContent = "Sign in with Nostr";
    });
  }

  function extractToken(raw) {
    /* Accept a bare token or a full private link — the fragment after
       '#' carries the bearer token (§5.4 contract). */
    raw = String(raw || "").trim();
    var hashIdx = raw.indexOf("#");
    if (hashIdx >= 0) raw = raw.slice(hashIdx + 1);
    return raw;
  }

  function doClaim() {
    var input = document.getElementById("gm-claim-input");
    var msg = document.getElementById("gm-claim-msg");
    if (!input || !msg) return;
    var token = extractToken(input.value);
    if (!token) {
      msg.textContent = "Paste your private order link first.";
      return;
    }
    msg.textContent = "";
    api("/nostr/claim", {
      method: "POST",
      body: JSON.stringify({ token: token })
    }).then(function (res) {
      if (res.status === 200) {
        msg.textContent = "Order linked — it now appears in your history.";
        input.value = "";
        return loadOrders();
      }
      msg.textContent =
        "That link could not be linked. Check the link and try again.";
    });
  }

  /* --- wiring ----------------------------------------------------------- */

  btn.addEventListener("click", function () {
    if (state.signedIn) {
      /* Toggle the orders panel. */
      panel.hidden = !panel.hidden;
      if (!panel.hidden && !panel.childNodes.length) loadOrders();
      return;
    }
    doSignIn();
  });

  /* Signed-in detection probes the session once per page view — a 401 is
     the normal signed-out signal (no cookie is readable from JS). */
  loadOrders().then(function (signedIn) {
    if (!signedIn) {
      panel.hidden = true;
    }
  });
})();
