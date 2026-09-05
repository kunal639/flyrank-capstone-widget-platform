// frontend/widget/widget.js
(function () {
  "use strict";

  // 1. Locate the calling script tag
  var currentScript =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      return scripts[scripts.length - 1];
    })();

  if (!currentScript) {
    console.error("[FlyRank Widget] Unable to locate loader script tag.");
    return;
  }

  var widgetId = currentScript.getAttribute("data-widget-id");
  if (!widgetId) {
    console.error("[FlyRank Widget] Missing required data-widget-id attribute.");
    return;
  }

  // Derive API base URL from data-api-base or script source
  var apiBase = currentScript.getAttribute("data-api-base");
  if (!apiBase) {
    try {
      var url = new URL(currentScript.src);
      apiBase = url.origin;
    } catch (e) {
      apiBase = window.location.origin;
    }
  }
  // Trim trailing slash
  apiBase = apiBase.replace(/\/+$/, "");

  // 2. Inject CSS if not already present
  var cssHref = apiBase + "/static/widget.css";
  if (!document.querySelector('link[href="' + cssHref + '"]')) {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.type = "text/css";
    link.href = cssHref;
    document.head.appendChild(link);
  }

  // 3. Create Root Mount Point
  var mountPoint = document.createElement("div");
  mountPoint.className = "fw-widget-container";
  mountPoint.innerHTML = '<p class="fw-label">Loading widget...</p>';
  currentScript.parentNode.insertBefore(mountPoint, currentScript.nextSibling);

  // 4. Generate UUID v4 for idempotency
  function generateUUID() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0,
        v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // 5. Fetch Public Config
  fetch(apiBase + "/widgets/" + encodeURIComponent(widgetId) + "/config", {
    method: "GET",
    headers: { Accept: "application/json" }
  })
    .then(function (res) {
      if (!res.ok) {
        throw new Error("HTTP error " + res.status);
      }
      return res.json();
    })
    .then(function (config) {
      renderWidget(config);
    })
    .catch(function (err) {
      console.error("[FlyRank Widget] Failed to load configuration:", err);
      mountPoint.innerHTML =
        '<div class="fw-alert fw-alert-error">Failed to load widget. Please try again later.</div>';
    });

  // 6. Form Renderer
  function renderWidget(config) {
    mountPoint.innerHTML = "";

    var title = document.createElement("h3");
    title.className = "fw-widget-title";
    title.textContent = config.title || "Contact Us";
    mountPoint.appendChild(title);

    var messageContainer = document.createElement("div");
    mountPoint.appendChild(messageContainer);

    var form = document.createElement("form");
    form.noValidate = true;

    // Honeypot Field (hidden from humans, filled by dumb bots)
    var hpWrapper = document.createElement("div");
    hpWrapper.className = "fw-hidden-honeypot";
    hpWrapper.setAttribute("aria-hidden", "true");
    var hpInput = document.createElement("input");
    hpInput.type = "text";
    hpInput.name = "website_hp";
    hpInput.tabIndex = -1;
    hpInput.autocomplete = "off";
    hpWrapper.appendChild(hpInput);
    form.appendChild(hpWrapper);

    // Dynamic Fields (ordered by server display_order)
    var fields = config.fields || [];
    fields.forEach(function (field) {
      var group = document.createElement("div");
      group.className = "fw-field-group";

      var label = document.createElement("label");
      label.className = "fw-label";
      label.textContent = field.name.charAt(0).toUpperCase() + field.name.slice(1);

      if (field.required) {
        var reqMark = document.createElement("span");
        reqMark.className = "fw-required-mark";
        reqMark.textContent = "*";
        label.appendChild(reqMark);
      }

      var input;
      if (field.type === "textarea") {
        input = document.createElement("textarea");
        input.className = "fw-textarea";
      } else {
        input = document.createElement("input");
        input.className = "fw-input";
        input.type = field.type === "email" ? "email" : field.type === "number" ? "number" : "text";
      }

      input.name = field.name;
      input.required = !!field.required;
      input.setAttribute("data-field-id", field.field_id);
      input.setAttribute("data-field-type", field.type);

      group.appendChild(label);
      group.appendChild(input);
      form.appendChild(group);
    });

    // Submit Button
    var submitBtn = document.createElement("button");
    submitBtn.type = "submit";
    submitBtn.className = "fw-btn-submit";
    submitBtn.textContent = "Submit";
    form.appendChild(submitBtn);

    mountPoint.appendChild(form);

    // 7. Form Submission Handler
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      messageContainer.innerHTML = "";

      // Client-side quick UX validation
      var hasError = false;
      var fieldInputs = form.querySelectorAll("[data-field-id]");
      for (var i = 0; i < fieldInputs.length; i++) {
        var inp = fieldInputs[i];
        if (inp.required && !inp.value.trim()) {
          hasError = true;
          break;
        }
      }

      if (hasError) {
        messageContainer.innerHTML =
          '<div class="fw-alert fw-alert-error">Please fill in all required fields.</div>';
        return;
      }

      // Collect Field Values
      var submittedFields = {};
      fieldInputs.forEach(function (inp) {
        var val = inp.value.trim();
        var fType = inp.getAttribute("data-field-type");
        if (fType === "number" && val !== "") {
          submittedFields[inp.name] = Number(val);
        } else {
          submittedFields[inp.name] = val;
        }
      });

      // Prepare Payload adhering exactly to docs/api.md
      var payload = {
        widget_id: widgetId,
        idempotency_key: generateUUID(),
        honeypot: hpInput.value,
        fields: submittedFields
      };

      // Loading state
      submitBtn.disabled = true;
      submitBtn.textContent = "Sending...";

      fetch(apiBase + "/submissions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json"
        },
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          if (res.status === 201) {
            return res.json().then(function () {
              form.style.display = "none";
              messageContainer.innerHTML =
                '<div class="fw-alert fw-alert-success">Thanks! Your submission was received.</div>';
            });
          } else {
            return res.json().catch(function () { return {}; }).then(function () {
              messageContainer.innerHTML =
                '<div class="fw-alert fw-alert-error">Something went wrong. Please try again.</div>';
            });
          }
        })
        .catch(function (networkErr) {
          console.error("[FlyRank Widget] Submission failed:", networkErr);
          messageContainer.innerHTML =
            '<div class="fw-alert fw-alert-error">Unable to send submission. Check your connection.</div>';
        })
        .finally(function () {
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit";
        });
    });
  }
})();