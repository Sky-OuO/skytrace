(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.add("js");

  if (window.htmx) {
    htmx.config.globalViewTransitions = !reduce;
    htmx.config.scrollBehavior = reduce ? "auto" : "smooth";
  }

  function onScroll() {
    document.documentElement.classList.toggle("is-scrolled", window.scrollY > 8);
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  function phColor(key) {
    var h = 0;
    var text = String(key || "sky");
    for (var i = 0; i < text.length; i++) h = (h * 33 + text.charCodeAt(i)) >>> 0;
    return "hsl(32 8% " + (74 + (h % 12)) + "%)";
  }

  function arm(img) {
    if (img.dataset.armed) return;
    img.dataset.armed = "1";
    var frame = img.closest(".frame");
    if (frame) frame.style.setProperty("--ph", phColor(img.getAttribute("data-shot") || img.currentSrc || img.src));
    var show = function () { img.classList.add("is-in"); };
    if (reduce || (img.complete && img.naturalWidth)) show();
    else img.addEventListener("load", show, { once: true });
  }

  function armAll(root) {
    (root || document).querySelectorAll(".frame img").forEach(arm);
  }

  var sectionObserver = null;
  function watchSections() {
    if (sectionObserver) sectionObserver.disconnect();
    var nav = document.querySelector(".section-nav");
    if (!nav || !("IntersectionObserver" in window)) return;
    var links = Array.prototype.slice.call(nav.querySelectorAll('a[href^="#"]'));
    var pairs = [];
    links.forEach(function (link) {
      var section = document.getElementById(link.getAttribute("href").slice(1));
      if (section) pairs.push([section, link]);
    });
    sectionObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (link) { link.removeAttribute("aria-current"); });
        var match = pairs.find(function (pair) { return pair[0] === entry.target; });
        if (match) match[1].setAttribute("aria-current", "true");
      });
    }, { rootMargin: "-30% 0px -55% 0px", threshold: 0.01 });
    pairs.forEach(function (pair) { sectionObserver.observe(pair[0]); });
  }

  function toast(message) {
    var el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add("is-on");
    clearTimeout(el._hide);
    el._hide = setTimeout(function () { el.classList.remove("is-on"); }, 3200);
  }

  function skeleton() {
    return '<article class="card skeleton" aria-hidden="true"><span class="frame" style="aspect-ratio:3/4"></span><span class="card-body"><span class="sk"></span><span class="sk short"></span></span></article>';
  }

  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  var restoring = false;

  function saveFeedScroll() {
    if (restoring || !document.getElementById("feed")) return;
    sessionStorage.setItem("skytrace-feed-scroll", String(window.scrollY));
    sessionStorage.setItem("skytrace-feed-path", location.pathname + location.search);
  }

  function restoreFeedScroll() {
    var path = sessionStorage.getItem("skytrace-feed-path");
    if (path !== location.pathname + location.search) return;
    if (!document.getElementById("feed")) return;
    var y = Number(sessionStorage.getItem("skytrace-feed-scroll") || "0");
    if (y <= 0) return;
    restoring = true;
    var tries = 0;
    var timer = setInterval(function () {
      if (document.getElementById("feed")) window.scrollTo(0, y);
      tries += 1;
      if (tries >= 24) {
        clearInterval(timer);
        restoring = false;
      }
    }, 40);
  }

  document.addEventListener("click", function (event) {
    var card = event.target.closest("#feed a.card");
    if (card) saveFeedScroll();
    var pill = event.target.closest("[data-feed-filter]");
    if (pill) {
      document.querySelectorAll("[data-feed-filter]").forEach(function (el) { el.removeAttribute("aria-current"); });
      pill.setAttribute("aria-current", "page");
    }
    var summary = event.target.closest(".example-fold summary");
    if (!summary || reduce) return;
    var details = summary.parentElement;
    var fold = details.querySelector(".fold");
    if (!fold) return;
    event.preventDefault();
    if (details.open) {
      fold.style.height = fold.scrollHeight + "px";
      requestAnimationFrame(function () { fold.style.height = "0px"; });
      fold.addEventListener("transitionend", function done() {
        details.open = false;
        fold.style.height = "";
      }, { once: true });
    } else {
      details.open = true;
      var full = fold.scrollHeight;
      fold.style.height = "0px";
      requestAnimationFrame(function () { fold.style.height = full + "px"; });
      fold.addEventListener("transitionend", function () { fold.style.height = "auto"; }, { once: true });
    }
  });

  window.addEventListener("pageshow", restoreFeedScroll);
  window.addEventListener("popstate", restoreFeedScroll);
  document.addEventListener("htmx:historyRestore", restoreFeedScroll);
  document.addEventListener("htmx:afterSettle", restoreFeedScroll);
  document.addEventListener("htmx:afterSettle", function () {
    armAll();
    watchSections();
    document.querySelectorAll(".drop").forEach(bindDrop);
    document.querySelectorAll("form.publish-form").forEach(bindPublish);
    document.querySelectorAll("form.review-form").forEach(bindReview);
  });
  document.addEventListener("htmx:beforeRequest", function (event) {
    var el = event.detail.elt;
    if (el && el.classList.contains("feed-sentinel")) {
      el.insertAdjacentHTML("beforebegin", skeleton() + skeleton());
    }
    if (el && el.hasAttribute("data-feed-filter")) {
      var feed = document.getElementById("feed");
      if (feed) feed.insertAdjacentHTML("afterbegin", skeleton() + skeleton());
    }
  });
  document.addEventListener("htmx:afterSwap", function () {
    document.querySelectorAll(".card.skeleton").forEach(function (node) { node.remove(); });
  });

  function bindDrop(drop) {
    if (drop.dataset.bound) return;
    drop.dataset.bound = "1";
    var input = drop.querySelector('input[type="file"]');
    var preview = drop.querySelector("img");
    var hint = drop.querySelector(".drop-hint");
    if (!input) return;
    function show(file) {
      if (!file || !preview) return;
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
      preview.classList.add("is-in");
      if (hint) hint.hidden = true;
      drop.classList.remove("is-invalid");
    }
    input.addEventListener("change", function () { show(input.files && input.files[0]); });
    ["dragenter", "dragover"].forEach(function (name) {
      drop.addEventListener(name, function (event) {
        event.preventDefault();
        drop.classList.add("is-hot");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      drop.addEventListener(name, function (event) {
        event.preventDefault();
        drop.classList.remove("is-hot");
      });
    });
    drop.addEventListener("drop", function (event) {
      var file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (!file || !input) return;
      var transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      show(file);
    });
  }

  function validatePublish(form) {
    var ok = true;
    form.querySelectorAll(".is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
    form.querySelectorAll(".field-error").forEach(function (el) { el.remove(); });
    function fail(node, message) {
      ok = false;
      var field = node.closest(".field, .drop") || node;
      field.classList.add("is-invalid");
      var note = document.createElement("p");
      note.className = "field-error";
      note.setAttribute("role", "alert");
      note.textContent = message;
      field.appendChild(note);
    }
    var picked = form.querySelector('input[name="subject_slug"]:checked');
    if (!picked) fail(form.querySelector("#topic-q") || form, "请选择题材，或选待归类");
    var type = form.querySelector('[name="type"]');
    var file = form.querySelector('#image');
    if (type && type.value === "finished" && file && (!file.files || !file.files.length)) {
      fail(file, "成片需要一张图");
    }
    form.querySelectorAll("[data-required]").forEach(function (field) {
      if (!field.value.trim()) fail(field, "这里需要写一句");
    });
    var sentence = form.querySelector("#body");
    if (type && type.value === "finished" && sentence && !sentence.value.trim()) fail(sentence, "写一句这张怎么拍的");
    var auth = form.querySelector('input[name="portrait_auth"]');
    if (auth && !auth.checked) fail(auth, "人像需要勾选可展示");
    return ok;
  }

  function formAction(form) {
    // A control named "action" shadows HTMLFormElement.action and returns a RadioNodeList.
    return form.getAttribute("action") || window.location.pathname;
  }

  function formData(form, submitter) {
    try {
      if (submitter) return new FormData(form, submitter);
    } catch (err) {
      /* Older browsers reject the submitter argument. */
    }
    var data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    return data;
  }

  function bindPublish(form) {
    if (form.dataset.bound) return;
    form.dataset.bound = "1";
    form.addEventListener("submit", function (event) {
      if (!validatePublish(form)) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      var submitter = event.submitter;
      var data = formData(form, submitter);
      var buttons = form.querySelectorAll("button");
      buttons.forEach(function (button) { button.disabled = true; });
      fetch(formAction(form), { method: "POST", body: data, redirect: "manual", credentials: "same-origin" })
        .then(function (response) {
          if (response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
            var draft = submitter && submitter.value === "draft";
            toast(draft ? "已存成草稿。" : "已收到，当前是待审。还不会出现在首页。");
            return;
          }
          return response.text().then(function (html) {
            var doc = new DOMParser().parseFromString(html, "text/html");
            var alert = doc.querySelector("[role=alert]");
            toast(alert ? alert.textContent.trim() : "没有提交成功");
          });
        })
        .catch(function () { toast("网络没有送出去"); })
        .finally(function () { buttons.forEach(function (button) { button.disabled = false; }); });
    }, true);
  }

  function bindReview(form) {
    if (form.dataset.bound) return;
    form.dataset.bound = "1";
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var data = formData(form, event.submitter);
      var decision = data.get("decision");
      fetch(formAction(form), { method: "POST", body: data, redirect: "manual", credentials: "same-origin" })
        .then(function (response) {
          if (response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
            toast(decision === "rejected" ? "已驳回" : "已通过，待审结束");
            var card = form.closest(".review-card");
            if (card) card.remove();
            if (!document.querySelector(".review-card")) {
              var empty = document.createElement("p");
              empty.className = "empty-note";
              empty.textContent = "当前没有待处理工单。";
              document.querySelector(".wrap").appendChild(empty);
            }
            return;
          }
          toast("没有处理成功");
        })
        .catch(function () { toast("网络没有送出去"); });
    });
  }

  function boot() {
    armAll();
    watchSections();
    document.querySelectorAll(".drop").forEach(bindDrop);
    document.querySelectorAll("form.publish-form").forEach(bindPublish);
    document.querySelectorAll("form.review-form").forEach(bindReview);
    var seeded = document.querySelector("[data-toast]");
    if (seeded && seeded.textContent.trim()) toast(seeded.textContent.trim());
    document.querySelectorAll(".nav a").forEach(function (link) {
      if (link.getAttribute("aria-current") === "page") link.classList.add("is-on");
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
