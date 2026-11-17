(function () {
  "use strict";

  const MAX_STICKERS = 12;
  const BASE_FONT = 24;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function csrfToken() {
    const input = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  /* ------------------------------ стикер-студия ------------------------------ */
  function initStudio() {
    const canvas = document.getElementById("stubCanvas");
    if (!canvas) return;
    const palette = document.getElementById("stickerPalette");
    const body = canvas.querySelector(".cup-body");
    const countLabel = document.getElementById("stickersCount");
    const statusLabel = document.getElementById("designStatus");
    const saveUrl = canvas.dataset.saveUrl;
    const clearUrl = canvas.dataset.clearUrl;
    const checkoutUrl = canvas.dataset.checkoutUrl;

    let state = Array.from(body.querySelectorAll(".cup-placed")).map(function (el) {
      return {
        sticker: Number(el.dataset.sticker),
        symbol: el.textContent.trim(),
        x: Number(el.dataset.x) || 50,
        y: Number(el.dataset.y) || 50,
        scale: Number(el.dataset.scale) || 1,
        rotation: Number(el.dataset.rotation) || 0,
      };
    });
    let selected = -1;

    function status(text) {
      if (statusLabel) statusLabel.textContent = text;
    }

    function render() {
      body.querySelectorAll(".cup-placed").forEach(function (el) { el.remove(); });
      state.forEach(function (item, index) {
        const el = document.createElement("span");
        el.className = "cup-placed" + (index === selected ? " selected" : "");
        el.dataset.index = String(index);
        el.textContent = item.symbol;
        el.style.left = item.x + "%";
        el.style.top = item.y + "%";
        el.style.fontSize = BASE_FONT * item.scale + "px";
        el.style.transform = "translate(-50%, -50%) rotate(" + item.rotation + "deg)";
        body.appendChild(el);
      });
      if (countLabel) countLabel.textContent = state.length + " / " + MAX_STICKERS;
    }

    function select(index) {
      selected = index;
      body.querySelectorAll(".cup-placed").forEach(function (el) {
        el.classList.toggle("selected", Number(el.dataset.index) === index);
      });
      if (index < 0) {
        status("Выберите стикер, чтобы изменить его размер и поворот.");
      } else {
        const item = state[index];
        status("Выбран «" + item.symbol + "»: " + Math.round(item.scale * 100) + "%, поворот " + item.rotation + "°.");
      }
    }

    function payload() {
      return state.map(function (item) {
        return {
          sticker: item.sticker,
          x: Math.round(item.x * 10) / 10,
          y: Math.round(item.y * 10) / 10,
          scale: Math.round(item.scale * 100) / 100,
          rotation: Math.round(item.rotation),
        };
      });
    }

    async function save(silent) {
      if (!silent) status("Сохраняем дизайн…");
      try {
        const response = await fetch(saveUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
          body: JSON.stringify({ stickers: payload() }),
        });
        const data = await response.json().catch(function () { return {}; });
        if (!response.ok || !data.ok) throw new Error(data.error || "Не удалось сохранить");
        status(data.saved ? "Дизайн сохранён: " + data.saved + " стик. Перейдёт в заказ." : "Дизайн пуст — стакан будет без стикеров.");
        return true;
      } catch (error) {
        status("Ошибка сохранения: " + error.message + ". Попробуйте ещё раз.");
        return false;
      }
    }

    function addSticker(id, symbol, x, y) {
      if (state.length >= MAX_STICKERS) {
        status("На стакане уже " + MAX_STICKERS + " стикеров — это максимум.");
        return;
      }
      state.push({ sticker: id, symbol: symbol, x: x, y: y, scale: 1, rotation: 0 });
      selected = state.length - 1;
      render();
      select(selected);
      save(true);
    }

    /* палитра: drag-and-drop и клик */
    if (palette) {
      palette.addEventListener("dragstart", function (event) {
        const button = event.target.closest(".sticker-btn");
        if (!button) return;
        event.dataTransfer.setData("text/plain", button.dataset.sticker);
        event.dataTransfer.effectAllowed = "copy";
      });
      palette.addEventListener("click", function (event) {
        const button = event.target.closest(".sticker-btn");
        if (!button) return;
        addSticker(Number(button.dataset.sticker), button.dataset.symbol, 50, 50);
      });
    }

    body.addEventListener("dragover", function (event) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    });

    body.addEventListener("drop", function (event) {
      event.preventDefault();
      const id = Number(event.dataTransfer.getData("text/plain"));
      const found = (window.STICKERS || []).find(function (item) { return item.id === id; });
      if (!found) return;
      const rect = body.getBoundingClientRect();
      addSticker(
        found.id,
        found.symbol,
        clamp(((event.clientX - rect.left) / rect.width) * 100, 2, 98),
        clamp(((event.clientY - rect.top) / rect.height) * 100, 2, 98)
      );
    });

    /* перетаскивание стикеров внутри стакана */
    let drag = null;
    body.addEventListener("pointerdown", function (event) {
      const el = event.target.closest(".cup-placed");
      if (!el) {
        select(-1);
        return;
      }
      const index = Number(el.dataset.index);
      select(index);
      const rect = body.getBoundingClientRect();
      drag = {
        index: index,
        element: el,
        rect: rect,
        startX: event.clientX,
        startY: event.clientY,
        originX: state[index].x,
        originY: state[index].y,
        moved: false,
      };
      el.setPointerCapture(event.pointerId);
      el.style.cursor = "grabbing";
      event.preventDefault();
    });

    body.addEventListener("pointermove", function (event) {
      if (!drag) return;
      const dx = ((event.clientX - drag.startX) / drag.rect.width) * 100;
      const dy = ((event.clientY - drag.startY) / drag.rect.height) * 100;
      if (Math.abs(dx) + Math.abs(dy) > 1) drag.moved = true;
      const item = state[drag.index];
      item.x = clamp(drag.originX + dx, 2, 98);
      item.y = clamp(drag.originY + dy, 2, 98);
      drag.element.style.left = item.x + "%";
      drag.element.style.top = item.y + "%";
    });

    function endDrag(event) {
      if (!drag) return;
      drag.element.style.cursor = "grab";
      const moved = drag.moved;
      drag = null;
      if (moved) save(true);
    }
    body.addEventListener("pointerup", endDrag);
    body.addEventListener("pointercancel", endDrag);

    /* кнопки управления */
    document.querySelectorAll("[data-action]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (selected < 0) {
          status("Сначала выберите стикер на стакане.");
          return;
        }
        const item = state[selected];
        const action = button.dataset.action;
        if (action === "bigger") item.scale = clamp(item.scale + 0.15, 0.5, 2.5);
        if (action === "smaller") item.scale = clamp(item.scale - 0.15, 0.5, 2.5);
        if (action === "rotate") item.rotation = item.rotation >= 165 ? -180 : item.rotation + 15;
        if (action === "remove") {
          state.splice(selected, 1);
          selected = -1;
          render();
          select(-1);
          save(true);
          return;
        }
        render();
        select(selected);
        save(true);
      });
    });

    const saveButton = document.getElementById("saveDesign");
    if (saveButton) saveButton.addEventListener("click", function () { save(false); });

    const cartButton = document.getElementById("designToCart");
    if (cartButton) {
      cartButton.addEventListener("click", async function () {
        cartButton.disabled = true;
        const ok = await save(false);
        if (ok) {
          window.location.href = checkoutUrl;
        } else {
          cartButton.disabled = false;
        }
      });
    }

    const clearButton = document.getElementById("clearDesign");
    if (clearButton) {
      clearButton.addEventListener("click", async function () {
        if (state.length && !window.confirm("Убрать все стикеры со стакана?")) return;
        try {
          await fetch(clearUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken() } });
        } catch (error) {
          status("Не удалось очистить дизайн — проверьте соединение.");
          return;
        }
        state = [];
        selected = -1;
        render();
        select(-1);
        status("Дизайн очищен.");
      });
    }

    render();
    select(-1);
  }

  /* ------------------------------ прочее ------------------------------ */
  function initAlerts() {
    document.querySelectorAll(".alert-dismissible").forEach(function (alert) {
      window.setTimeout(function () {
        if (!alert.isConnected || !window.bootstrap) return;
        window.bootstrap.Alert.getOrCreateInstance(alert).close();
      }, 6000);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initStudio();
    initAlerts();
  });
})();
