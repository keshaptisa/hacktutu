const basketTitle = document.querySelector("#basket-title");
const basketCopy = document.querySelector("#basket-copy");
const basketGrid = document.querySelector("#basket-grid");

function formatBudget(value) {
  return `${Math.round(Number(value) || 0).toLocaleString("ru-RU")} ₽`;
}

function getParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    escapeId: params.get("escape_id"),
    scenarioId: params.get("scenario_id"),
  };
}

function renderCard(item) {
  const card = document.createElement("article");
  card.className = "basket-item";
  card.innerHTML = `
    <span class="selected-label">${item.title}</span>
    <strong>${item.label}</strong>
    <p>Переход ведет на страницу оформления на Туту.</p>
    <button class="cta-button" type="button">Открыть на Туту →</button>
  `;
  card.querySelector("button").addEventListener("click", () => {
    window.open(item.url, "_blank", "noopener");
  });
  return card;
}

function renderMissing(missing) {
  if (!missing.length) return;
  const card = document.createElement("article");
  card.className = "basket-item";
  const list = missing.map((item) => `<li>${item}</li>`).join("");
  card.innerHTML = `
    <span class="selected-label">Не пришло</span>
    <strong>Эти части сценария пока без ссылки</strong>
    <ul>${list}</ul>
  `;
  basketGrid.append(card);
}

async function loadBasket() {
  const { escapeId, scenarioId } = getParams();
  if (!escapeId || !scenarioId) {
    basketTitle.textContent = "Не хватает параметров корзины";
    basketCopy.textContent = "Вернись на главный экран, выбери сценарий заново и открой покупку еще раз.";
    return;
  }

  try {
    const response = await fetch(
      `/api/escape/${encodeURIComponent(escapeId)}/scenario/${encodeURIComponent(scenarioId)}/purchase`
    );
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      throw new Error((data && data.error && data.error.message) || "Не удалось загрузить ссылки");
    }

    basketTitle.textContent = `${data.title} · ${data.destination}`;
    basketCopy.textContent =
      data.items.length > 0
        ? `Нашли ${data.items.length} ссылок на оформление. Итоговый бюджет сценария: ${formatBudget(data.total_price_rub)}.`
        : "Сценарий собран, но ссылки на оформление для этого маршрута пока недоступны.";

    basketGrid.innerHTML = "";
    data.items.forEach((item) => {
      basketGrid.append(renderCard(item));
    });
    renderMissing(data.missing || []);
  } catch (error) {
    basketTitle.textContent = "Не удалось открыть корзину";
    basketCopy.textContent = error.message || "Попробуй открыть сценарий еще раз.";
  }
}

loadBasket();
