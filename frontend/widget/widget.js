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

  // 3. Create Root Mount Point (placed right after the script tag)
  var mountPoint = document.createElement("div");
  mountPoint.className = "fw-widget-container";
  mountPoint.innerHTML = '<p class="fw-label">Loading form...</p>';
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
        throw new Error("HTTP " + res.status);
      }
      return res.json();
    })
    .then(function (config) {
      renderWidget(config);
    })
    .catch(function (err) {
      console.warn("[FlyRank Widget] Failed to load configuration:", err.message);
      mountPoint.innerHTML =
        '<div class="fw-alert fw-alert-error">Unable to load form right now. Please try again later.</div>';
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

    // Honeypot Field (hidden from humans, filled by spam bots)
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
        reqMark.textContent = " *";
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

      // Quick Client-Side Validation
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

      var payload = {
        widget_id: widgetId,
        idempotency_key: generateUUID(),
        honeypot: hpInput.value,
        fields: submittedFields
      };

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
            form.style.display = "none";
            messageContainer.innerHTML =
              '<div class="fw-alert fw-alert-success">Thanks! Your submission was received.</div>';
            return;
          }

          // Polite client messaging with console status warning
          console.warn("[FlyRank Widget] Submission response status:", res.status);

          if (res.status === 429) {
            messageContainer.innerHTML =
              '<div class="fw-alert fw-alert-error">Too many attempts. Please wait a moment and try again.</div>';
          } else if (res.status === 403) {
            messageContainer.innerHTML =
              '<div class="fw-alert fw-alert-error">Submissions from this website domain are not permitted.</div>';
          } else if (res.status === 413) {
            messageContainer.innerHTML =
              '<div class="fw-alert fw-alert-error">Your submission is too large. Please shorten your message.</div>';
          } else {
            messageContainer.innerHTML =
              '<div class="fw-alert fw-alert-error">Submission could not be completed. Please check your inputs.</div>';
          }
        })
        .catch(function (networkErr) {
          console.error("[FlyRank Widget] Submission network failure:", networkErr);
          messageContainer.innerHTML =
            '<div class="fw-alert fw-alert-error">Network error. Please check your connection and try again.</div>';
        })
        .finally(function () {
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit";
        });
    });
  }
})();