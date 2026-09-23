/* admin_catalog.js — B3 catalog management (UI-SPEC §B3).

   Dense lists for products / collections / shipping with draft badges,
   visibility pills, soft-delete dialogs (tombstone disclosure verbatim),
   and a read-only unsigned-event dry-run viewer. Every mutating control
   carries a text label — no icon-only mutators. */
(function () {
  "use strict";

  var PRODUCT_TYPES = ["simple", "variable", "variation"];
  var FORMATS = ["digital", "physical"];
  var VISIBILITIES = ["on-sale", "hidden", "pre-order"];
  var SERVICES = ["standard", "express", "overnight", "pickup"];
  var DURATION_UNITS = ["H", "D", "W"];

  var DELETE_DISCLOSURE =
    "This is a soft delete. A deletion tombstone is published, but" +
    " removal from every relay and client cannot be guaranteed.";
  var IMAGE_DISCLOSURE = "Remote image hosts can learn viewer IP and time";

  window.app.mixin({
    data: function () {
      return {
        gmCatalog: {
          loading: false,
          error: null,
          tab: "products",
          catalogs: [],
          products: [],
          collections: [],
          shipping: [],
          services: SERVICES,
          productTypes: PRODUCT_TYPES,
          formats: FORMATS,
          visibilities: VISIBILITIES,
          durationUnits: DURATION_UNITS,
          imageDisclosure: IMAGE_DISCLOSURE,
          deleteDisclosure: DELETE_DISCLOSURE,
          editor: {
            show: false, saving: false, error: null, isNew: true,
            form: {}
          },
          collectionEditor: {
            show: false, saving: false, error: null, isNew: true,
            form: {}
          },
          shippingEditor: {
            show: false, saving: false, error: null, isNew: true,
            form: {}
          },
          deleteDialog: {
            show: false, kind: "", id: "", title: "", refs: null,
            busy: false
          },
          dryRun: { show: false, json: "", loading: false }
        }
      };
    },
    computed: {
      gmProductRows: function () {
        return this.gmCatalog.products.map(function (p) {
          var stock =
            p.stock_on_hand === null || p.stock_on_hand === undefined
              ? "Unlimited"
              : String((p.stock_on_hand || 0) - (p.stock_reserved || 0));
          return Object.assign({}, p, {
            _stock: stock,
            _price:
              (p.amount_minor === null || p.amount_minor === undefined
                ? "—"
                : p.amount_minor + " " + (p.currency || "SAT"))
          });
        });
      }
    },
    methods: {
      gmLoadCatalog: async function () {
        var self = this;
        self.gmCatalog.loading = true;
        self.gmCatalog.error = null;
        try {
          var res = await Promise.all([
            self.gmApi("GET", "/catalogs"),
            self.gmApi("GET", "/products"),
            self.gmApi("GET", "/collections"),
            self.gmApi("GET", "/shipping")
          ]);
          self.gmCatalog.catalogs = res[0];
          self.gmCatalog.products = res[1];
          self.gmCatalog.collections = res[2];
          self.gmCatalog.shipping = res[3];
        } catch (e) {
          self.gmCatalog.error = self.gmProblemCopy(e.problem);
        }
        self.gmCatalog.loading = false;
      },

      /* --- products ---------------------------------------------------- */
      gmNewProduct: function () {
        this.gmCatalog.editor = {
          show: true, saving: false, error: null, isNew: true,
          form: {
            catalog_id: this.gmCatalog.catalogs.length
              ? this.gmCatalog.catalogs[0].id
              : "",
            title: "", summary: "", description_md: "",
            product_type: "simple", format: "digital",
            amount_minor: 0, currency: "SAT",
            visibility: "on-sale", draft: false,
            stock_on_hand: null,
            parent_product_id: "",
            collection_ids: [], images_text: ""
          }
        };
      },
      gmEditProduct: async function (row) {
        var self = this;
        var d = await self.gmApi("GET", "/products/" + row.id);
        self.gmCatalog.editor = {
          show: true, saving: false, error: null, isNew: false,
          form: {
            id: d.id,
            catalog_id: d.catalog_id,
            title: d.title || "", summary: d.summary || "",
            description_md: d.description_md || "",
            product_type: d.product_type || "simple",
            format: d.format || "digital",
            amount_minor: d.amount_minor || 0,
            currency: d.currency || "SAT",
            visibility: d.visibility || "on-sale",
            draft: !!d.draft,
            stock_on_hand: d.stock_on_hand,
            parent_product_id: d.parent_product_id || "",
            collection_ids: d.collection_ids || [],
            images_text: (d.images || [])
              .map(function (i) { return i.url; })
              .join("\n")
          }
        };
      },
      gmSaveProduct: async function () {
        var self = this;
        var ed = self.gmCatalog.editor;
        ed.saving = true;
        ed.error = null;
        var f = ed.form;
        var body = {
          catalog_id: f.catalog_id,
          title: f.title,
          summary: f.summary || undefined,
          description_md: f.description_md || undefined,
          product_type: f.product_type,
          format: f.format,
          amount_minor: Number(f.amount_minor) || 0,
          currency: f.currency || "SAT",
          visibility: f.visibility,
          draft: !!f.draft,
          stock_on_hand:
            f.stock_on_hand === null || f.stock_on_hand === "" ||
              f.stock_on_hand === undefined
              ? null
              : Number(f.stock_on_hand),
          collection_ids: f.collection_ids || []
        };
        if (f.product_type === "variation" && f.parent_product_id) {
          body.parent_product_id = f.parent_product_id;
        }
        var images = (f.images_text || "")
          .split("\n")
          .map(function (s) { return s.trim(); })
          .filter(function (s) { return s.length; })
          .map(function (u) { return { url: u }; });
        if (images.length) body.images = images;
        try {
          if (ed.isNew) {
            await self.gmApi("POST", "/products", body);
          } else {
            await self.gmApi("PATCH", "/products/" + f.id, body);
          }
          ed.show = false;
          await self.gmLoadCatalog();
        } catch (e) {
          ed.error = self.gmProblemCopy(e.problem);
        }
        ed.saving = false;
      },
      gmDryRun: async function (row) {
        /* GET /products/{id}/events — rendered unsigned JSON viewer. */
        var self = this;
        self.gmCatalog.dryRun = { show: true, json: "", loading: true };
        try {
          var events = await self.gmApi(
            "GET", "/products/" + row.id + "/events"
          );
          self.gmCatalog.dryRun.json = JSON.stringify(events, null, 2);
        } catch (e) {
          self.gmCatalog.dryRun.json = self.gmProblemCopy(e.problem);
        }
        self.gmCatalog.dryRun.loading = false;
      },

      /* --- collections ---------------------------------------------------- */
      gmNewCollection: function () {
        this.gmCatalog.collectionEditor = {
          show: true, saving: false, error: null, isNew: true,
          form: { title: "", description: "", image: "", location: "" }
        };
      },
      gmEditCollection: function (row) {
        this.gmCatalog.collectionEditor = {
          show: true, saving: false, error: null, isNew: false,
          form: {
            id: row.id, title: row.title || "",
            description: row.description || "", image: row.image || "",
            location: row.location || ""
          }
        };
      },
      gmSaveCollection: async function () {
        var self = this;
        var ed = self.gmCatalog.collectionEditor;
        ed.saving = true;
        ed.error = null;
        var f = ed.form;
        var body = {
          title: f.title,
          description: f.description || undefined,
          image: f.image || undefined,
          location: f.location || undefined
        };
        try {
          if (ed.isNew) {
            await self.gmApi("POST", "/collections", body);
          } else {
            await self.gmApi("PATCH", "/collections/" + f.id, body);
          }
          ed.show = false;
          await self.gmLoadCatalog();
        } catch (e) {
          ed.error = self.gmProblemCopy(e.problem);
        }
        ed.saving = false;
      },

      /* --- shipping -------------------------------------------------------- */
      gmNewShipping: function () {
        this.gmCatalog.shippingEditor = {
          show: true, saving: false, error: null, isNew: true,
          form: {
            title: "", service: "standard", base_price_minor: 0,
            currency: "SAT", countries_text: "US", regions_text: "",
            duration_min: null, duration_max: null, duration_unit: "D",
            location: "", active: true
          }
        };
      },
      gmEditShipping: function (row) {
        this.gmCatalog.shippingEditor = {
          show: true, saving: false, error: null, isNew: false,
          form: {
            id: row.id, title: row.title || "",
            service: row.service || "standard",
            base_price_minor: row.base_price_minor || 0,
            currency: row.currency || "SAT",
            countries_text: (row.countries || []).join(", "),
            regions_text: (row.regions || []).join(", "),
            duration_min: row.duration_min, duration_max: row.duration_max,
            duration_unit: row.duration_unit || "D",
            location: row.location || "", active: row.active !== false
          }
        };
      },
      gmSaveShipping: async function () {
        var self = this;
        var ed = self.gmCatalog.shippingEditor;
        ed.saving = true;
        ed.error = null;
        var f = ed.form;
        var splitList = function (s) {
          return (s || "")
            .split(",")
            .map(function (x) { return x.trim().toUpperCase(); })
            .filter(function (x) { return x.length; });
        };
        var body = {
          title: f.title,
          service: f.service,
          base_price_minor: Number(f.base_price_minor) || 0,
          currency: f.currency || "SAT",
          countries: splitList(f.countries_text),
          regions: splitList(f.regions_text),
          duration_min:
            f.duration_min === null || f.duration_min === ""
              ? null
              : Number(f.duration_min),
          duration_max:
            f.duration_max === null || f.duration_max === ""
              ? null
              : Number(f.duration_max),
          duration_unit: f.duration_unit,
          location: f.location || undefined,
          active: !!f.active
        };
        try {
          if (ed.isNew) {
            await self.gmApi("POST", "/shipping", body);
          } else {
            await self.gmApi("PATCH", "/shipping/" + f.id, body);
          }
          ed.show = false;
          await self.gmLoadCatalog();
        } catch (e) {
          ed.error = self.gmProblemCopy(e.problem);
        }
        ed.saving = false;
      },

      /* --- soft delete (tombstone disclosure + strip choice) -------------- */
      gmAskDelete: function (kind, row) {
        this.gmCatalog.deleteDialog = {
          show: true, kind: kind, id: row.id,
          title: row.title || row.d_tag, refs: null, busy: false
        };
      },
      gmDeleteConfirm: async function (strip) {
        var self = this;
        var dlg = self.gmCatalog.deleteDialog;
        dlg.busy = true;
        var path =
          "/" +
          (dlg.kind === "collection"
            ? "collections"
            : dlg.kind === "shipping"
              ? "shipping"
              : "products") +
          "/" +
          dlg.id +
          (strip ? "?strip=true" : "");
        try {
          await self.gmApi("DELETE", path);
          dlg.show = false;
          await self.gmLoadCatalog();
        } catch (e) {
          /* 409 detail carries the reference report — offer the explicit
             strip-and-republish choice (spec §6.7). */
          if (e.status === 409) {
            dlg.refs = e.problem.detail || e.problem.title;
          } else {
            dlg.refs = self.gmProblemCopy(e.problem);
          }
        }
        dlg.busy = false;
      }
    },
    mounted: function () {
      if (window._gmCatalogWired) return;
      var vueEl = document.getElementById("vue");
      var root = vueEl && vueEl._vnode && vueEl._vnode.component;
      if (!root || !root.isMounted) return;
      if (!document.getElementById("gm-admin-root")) return;
      window._gmCatalogWired = true;
      var self = root.proxy;
      self.$watch("gm.merchant", function (m) {
        if (m && self.gm.view === "catalog") self.gmLoadCatalog();
      });
    }
  });
})();
