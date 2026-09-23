/* admin_publications.js — B2 publication health (PUB-02).

   Per-relay connection + ACK evidence labeled "delivery evidence" —
   relay delivery is NEVER presented as payment settlement. Outbox rows
   carry state pills, attempts, per-relay outcomes, supersession markers;
   partial publications name the missing relays; failed rows retry. */
(function () {
  "use strict";

  var KIND_LABELS = {
    0: "Profile",
    5: "Deletion",
    30402: "Product",
    30405: "Collection",
    30406: "Shipping",
    31989: "Handler",
    31990: "Handler info",
    order_msg: "Order message"
  };

  var STATE_PILLS = {
    pending: "Pending",
    claimed: "Claimed",
    publishing: "Publishing",
    partially_published: "Partially published",
    published: "Published",
    failed: "Failed",
    superseded: "Superseded"
  };

  window.app.mixin({
    data: function () {
      return {
        gmPubs: {
          loading: false,
          error: null,
          relays: [],
          defaults: { relays: [], blossom_servers: [] },
          blossomServers: [],
          intents: [],
          retrying: null,
          exceptionOrders: []
        }
      };
    },
    methods: {
      gmKindLabel: function (kind) {
        return KIND_LABELS[kind] || "Kind " + kind;
      },
      gmPubStateLabel: function (s) {
        return STATE_PILLS[s] || s;
      },
      /* Relays named in a partial publication — configured public
         targets minus the ones that returned a positive ACK. */
      gmMissingRelays: function (intent) {
        var pubs = intent.relay_publications || [];
        var accepted = {};
        pubs.forEach(function (p) {
          if (p.result === "accepted") accepted[p.relay_url] = true;
        });
        var targets = (this.gmPubs.relays || [])
          .filter(function (r) {
            return r.enabled &&
              (r.direction === "public" || r.direction === "both");
          })
          .map(function (r) {
            return r.relay_url;
          });
        var missing = targets.filter(function (r) {
          return !accepted[r];
        });
        if (missing.length) return missing;
        /* Fallback: publication rows that did not land an ACK. */
        return pubs
          .filter(function (p) { return p.result !== "accepted"; })
          .map(function (p) { return p.relay_url; });
      },
      gmLoadPublications: async function () {
        var self = this;
        var mid = self.gmMerchantId();
        if (!mid) return;
        self.gmPubs.loading = true;
        self.gmPubs.error = null;
        try {
          var res = await Promise.all([
            self.gmApi("GET", "/merchants/" + mid + "/relay-health"),
            self.gmApi("GET", "/merchants/" + mid + "/outbox"),
            self.gmApi(
              "GET",
              "/merchants/" + mid + "/orders?state=needs_attention"
            )
          ]);
          self.gmPubs.relays = res[0].relays || [];
          self.gmPubs.defaults = res[0].defaults || { relays: [] };
          self.gmPubs.blossomServers = res[0].blossom_servers || [];
          self.gmPubs.intents = res[1].intents || [];
          self.gmPubs.exceptionOrders = res[2] || [];
        } catch (e) {
          self.gmPubs.error = self.gmProblemCopy(e.problem);
        }
        self.gmPubs.loading = false;
      },
      gmRetryIntent: async function (intent) {
        var self = this;
        var mid = self.gmMerchantId();
        self.gmPubs.retrying = intent.id;
        try {
          await self.gmApi(
            "POST",
            "/merchants/" + mid + "/outbox/" + intent.id + "/retry",
            {}
          );
          await self.gmLoadPublications();
        } catch (e) {
          self.gmPubs.error = self.gmProblemCopy(e.problem);
        }
        self.gmPubs.retrying = null;
      },
      gmPubCellLabel: function (p) {
        if (!p) return "—";
        if (p.result === "accepted") return "ACKed";
        if (p.result === "rejected") return "Rejected";
        return "Failed";
      }
    },
    mounted: function () {
      if (window._gmPubsWired) return;
      if (!document.getElementById("gm-admin-root")) return;
      window._gmPubsWired = true;
      var self = this;
      self.$watch("gm.merchant", function (m) {
        if (m && self.gm.view === "publications") {
          self.gmLoadPublications();
        }
      });
    }
  });
})();
