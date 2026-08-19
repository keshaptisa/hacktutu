const API = "/api";

const statusMessages = [
  "Нормализуем пожелания",
  "Ищем направления под ваш ритм",
  "Сравниваем транспорт и время в пути",
  "Собираем разные сценарии поездки",
  "Поднимаем реальные ссылки бронирования",
];

const TRANSPORT_LABELS = {
  train: "Поезд",
  plane: "Самолет",
  bus: "Автобус",
  suburban: "Электричка",
  unknown: "Транспорт",
};

const budgetInput = document.querySelector("#budget");
const durationInput = document.querySelector("#duration");
const budgetValue = document.querySelector("#budget-value");
const durationValue = document.querySelector("#duration-value");
const moodGrid = document.querySelector("#mood-grid");
const tripForm = document.querySelector("#trip-form");
const promptInputs = Array.from(document.querySelectorAll(".prompt-grid input"));
const statusBoard = document.querySelector("#status-board");
const statusMain = document.querySelector("#status-main");
const statusSteps = document.querySelector("#status-steps");
const results = document.querySelector("#results");
const scenarioGrid = document.querySelector("#scenario-grid");
const detail = document.querySelector("#detail");
const closeDetailButton = document.querySelector("#close-detail");
const refineButton = document.querySelector("#refine-button");
const refineInput = document.querySelector("#refine-input");
const refineResult = document.querySelector("#refine-result");
const refineSummary = document.querySelector("#refine-summary");
const hotelGrid = document.querySelector("#hotel-grid");
const extrasGrid = document.querySelector("#excursion-grid");
const selectedHotelName = document.querySelector("#selected-hotel-name");
const selectedHotelMeta = document.querySelector("#selected-hotel-meta");
const selectedBookingName = document.querySelector("#selected-excursion-name");
const selectedBookingMeta = document.querySelector("#selected-excursion-meta");
const scenarioTemplate = document.querySelector("#scenario-template");
const optionTemplate = document.querySelector("#option-template");
const mcpStatus = document.querySelector("#mcp-status");
const buyButton = document.querySelector("#buy-button");
const purchaseNote = document.querySelector("#purchase-note");

const state = {
  escapeId: null,
  result: null,
  currentScenario: null,
  selectedMoods: new Set(["spontaneity", "impressions"]),
};

function formatBudget(value, approx = false) {
  const amount = Math.round(Number(value) || 0).toLocaleString("ru-RU");
  return `${approx ? "≈ " : ""}${amount} ₽`;
}

function pluralDays(days) {
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) return `${days} день`;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) {
    return `${days} дня`;
  }
  return `${days} дней`;
}

function pluralNights(nights) {
  const mod10 = nights % 10;
  const mod100 = nights % 100;
  if (mod10 === 1 && mod100 !== 11) return `${nights} ночь`;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) {
    return `${nights} ночи`;
  }
  return `${nights} ночей`;
}

function formatDuration(days) {
  return pluralDays(Number(days));
}

function formatDurationHours(hours) {
  const totalHours = Number(hours) || 0;
  if (totalHours < 24) return `${totalHours} ч`;
  return pluralDays(Math.round(totalHours / 24));
}

function transportLabel(kind) {
  return TRANSPORT_LABELS[kind] || TRANSPORT_LABELS.unknown;
}

function transportSummary(option) {
  if (!option) return "Маршрут подбирается";
  const pieces = [transportLabel(option.kind)];
  if (option.is_night_ride) pieces.push("ночной");
  if (option.transfers) {
    pieces.push(option.transfers === 1 ? "1 пересадка" : `${option.transfers} пересадки`);
  }
  return pieces.join(" • ");
}

function syncRanges() {
  budgetValue.textContent = formatBudget(budgetInput.value);
  durationValue.textContent = formatDuration(Number(durationInput.value));
}

function renderStatus(index) {
  statusSteps.innerHTML = "";
  statusMessages.forEach((message, position) => {
    const step = document.createElement("div");
    step.className = `status-step${position <= index ? " active" : ""}`;
    step.textContent = message;
    statusSteps.append(step);
  });
  statusMain.textContent = statusMessages[index];
}

function startStatusAnimation() {
  statusBoard.classList.remove("hidden");
  renderStatus(0);
  let index = 0;
  return window.setInterval(() => {
    index = Math.min(index + 1, statusMessages.length - 1);
    renderStatus(index);
  }, 700);
}

function renderMoods(moods) {
  moodGrid.innerHTML = "";
  moods.forEach((mood) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mood-chip";
    button.dataset.mood = mood.value;
    button.textContent = mood.label;
    if (state.selectedMoods.has(mood.value)) {
      button.classList.add("selected");
    }
    button.addEventListener("click", () => {
      if (state.selectedMoods.has(mood.value)) {
        state.selectedMoods.delete(mood.value);
        button.classList.remove("selected");
      } else {
        state.selectedMoods.add(mood.value);
        button.classList.add("selected");
      }
    });
    moodGrid.append(button);
  });
}

function defaultMoods() {
  return [
    { value: "spontaneity", label: "Спонтанность" },
    { value: "impressions", label: "Впечатления" },
    { value: "silence", label: "Тишина" },
    { value: "energy", label: "Энергия" },
    { value: "romance", label: "Романтика" },
    { value: "nightlife", label: "Ночная жизнь" },
  ];
}

function scenarioPills(scenario) {
  const pills = [
    formatBudget(scenario.total_price_rub, true),
    scenario.duration_label || formatDurationHours(scenario.duration_hours),
    transportLabel(scenario.transport && scenario.transport.kind),
  ];
  if (scenario.nights > 0) {
    pills.push(pluralNights(scenario.nights));
  }
  return pills;
}

function populateScenarios(scenarios) {
  scenarioGrid.innerHTML = "";
  scenarios.forEach((scenario) => {
    const node = scenarioTemplate.content.cloneNode(true);
    node.querySelector(".scenario-mode").textContent = scenario.title;
    node.querySelector(".scenario-city").textContent = scenario.destination;
    node.querySelector(".scenario-score").textContent = `${scenario.score.total} / 100`;
    node.querySelector(".scenario-copy").textContent = scenario.tagline;

    const meta = node.querySelector(".scenario-meta");
    scenarioPills(scenario).forEach((item) => {
      const pill = document.createElement("span");
      pill.textContent = item;
      meta.append(pill);
    });

    const reasons = node.querySelector(".scenario-reasons");
    scenario.reasons.slice(0, 3).forEach((reason) => {
      const li = document.createElement("li");
      li.textContent = reason;
      reasons.append(li);
    });

    node.querySelector(".scenario-button").addEventListener("click", () => {
      openScenarioDetail(scenario.id);
    });

    scenarioGrid.append(node);
  });
}

function renderResults(result) {
  populateScenarios(result.scenarios);
  results.classList.remove("hidden");
  if (result.degraded_reason) {
    statusMain.textContent = result.degraded_reason;
  } else if (result.normalized_summary) {
    statusMain.textContent = result.normalized_summary;
  } else {
    statusMain.textContent = "Маршруты собраны";
  }
}

function renderReasons(reasons) {
  const list = document.querySelector("#reason-list");
  list.innerHTML = "";
  reasons.forEach((reason) => {
    const item = document.createElement("li");
    item.textContent = reason;
    list.append(item);
  });
}

function renderTimeline(itinerary) {
  const timeline = document.querySelector("#timeline");
  timeline.innerHTML = "";

  if (!itinerary.length) {
    const card = document.createElement("article");
    card.className = "timeline-day";
    card.innerHTML = "<h4>Маршрут еще собирается</h4><div class='timeline-event'><div>Подробный таймлайн появится, как только подгрузятся детали поездки.</div></div>";
    timeline.append(card);
    return;
  }

  itinerary.forEach((day) => {
    const card = document.createElement("article");
    card.className = "timeline-day";

    const title = document.createElement("h4");
    title.textContent = day.headline ? `${day.weekday} • ${day.headline}` : day.weekday;
    card.append(title);

    day.events.forEach((event) => {
      const row = document.createElement("div");
      row.className = "timeline-event";

      const time = document.createElement("time");
      time.textContent = event.time;

      const body = document.createElement("div");
      body.textContent = event.detail ? `${event.title} — ${event.detail}` : event.title;

      row.append(time, body);
      card.append(row);
    });

    timeline.append(card);
  });
}

function clearOptionGrid(container) {
  container.innerHTML = "";
}

function createOptionCard(option) {
  const node = optionTemplate.content.cloneNode(true);
  const card = node.querySelector(".option-card");
  const media = node.querySelector(".option-media");
  const title = node.querySelector(".option-title");
  const subtitle = node.querySelector(".option-subtitle");
  const price = node.querySelector(".option-price");
  const copy = node.querySelector(".option-copy");
  const button = node.querySelector(".option-button");

  media.classList.add(`option-media--${option.theme || "violet"}`);
  if (option.imageUrl) {
    media.classList.add("option-media--photo");
    media.style.backgroundImage = `linear-gradient(180deg, rgba(17, 17, 45, 0.08), rgba(17, 17, 45, 0.38)), url("${option.imageUrl}")`;
  }
  media.textContent = option.badge || "";
  title.textContent = option.title;
  subtitle.textContent = option.subtitle;
  price.textContent = option.price;
  copy.textContent = option.description;
  button.textContent = option.buttonText;

  if (option.selected) {
    card.classList.add("selected");
  }

  if (option.onClick) {
    button.addEventListener("click", option.onClick);
  } else {
    button.disabled = true;
  }

  return node;
}

function renderHotel(scenario) {
  clearOptionGrid(hotelGrid);
  if (!scenario.hotel) {
    selectedHotelName.textContent = "Пока без отеля";
    selectedHotelMeta.textContent = "Для этого сценария проживание пока не подобралось.";
    hotelGrid.append(
      createOptionCard({
        badge: "HOTEL",
        title: "Проживание пока не найдено",
        subtitle: "Можно выбрать сценарий без отеля",
        price: "—",
        description: "Если появится подходящий вариант, он отобразится здесь вместе со ссылкой на бронирование.",
        buttonText: "Нет ссылки",
        theme: "sand",
      })
    );
    return;
  }

  const hotel = scenario.hotel;
  const hotelMeta = [];
  if (hotel.stars) hotelMeta.push(`${hotel.stars}★`);
  if (hotel.rating) hotelMeta.push(`рейтинг ${hotel.rating}`);
  if (hotel.district) hotelMeta.push(hotel.district);

  selectedHotelName.textContent = hotel.name;
  selectedHotelMeta.textContent = hotelMeta.length
    ? hotelMeta.join(" • ")
    : "Подобранный вариант проживания";

  hotelGrid.append(
    createOptionCard({
      badge: "HOTEL",
      title: hotel.name,
      subtitle: hotelMeta.join(" • ") || hotel.city,
      price: hotel.total_price_rub ? formatBudget(hotel.total_price_rub) : "Цена уточняется",
      imageUrl: hotel.image_url,
      description: hotel.purchase
        ? "Фото и ссылка на бронирование доступны в корзине."
        : "Отель добавлен в маршрут, но ссылка на бронирование пока недоступна.",
      buttonText: hotel.purchase ? "К корзине" : "В маршруте",
      selected: true,
      theme: "violet",
      onClick: hotel.purchase ? () => openBasket() : null,
    })
  );
}

function purchaseItemsFromScenario(scenario) {
  const items = [];
  if (scenario.transport && scenario.transport.purchase) {
    items.push({
      badge: "GO",
      title: "Туда",
      subtitle: scenario.transport.purchase.label,
      price: scenario.transport.price_rub ? formatBudget(scenario.transport.price_rub) : "Цена в Туту",
      description: `${transportLabel(scenario.transport.kind)} до ${scenario.transport.to_place}`,
      buttonText: "Открыть",
      theme: "orange",
      url: scenario.transport.purchase.url,
    });
  }
  if (scenario.return_transport && scenario.return_transport.purchase) {
    items.push({
      badge: "BACK",
      title: "Обратно",
      subtitle: scenario.return_transport.purchase.label,
      price: scenario.return_transport.price_rub ? formatBudget(scenario.return_transport.price_rub) : "Цена в Туту",
      description: `${transportLabel(scenario.return_transport.kind)} до ${scenario.return_transport.to_place}`,
      buttonText: "Открыть",
      theme: "teal",
      url: scenario.return_transport.purchase.url,
    });
  }
  if (scenario.hotel && scenario.hotel.purchase) {
    items.push({
      badge: "STAY",
      title: "Отель",
      subtitle: scenario.hotel.purchase.label,
      price: scenario.hotel.total_price_rub ? formatBudget(scenario.hotel.total_price_rub) : "Цена в Туту",
      description: scenario.hotel.name,
      buttonText: "Открыть",
      theme: "violet",
      url: scenario.hotel.purchase.url,
    });
  }
  return items;
}

function renderPurchaseOptions(scenario) {
  clearOptionGrid(extrasGrid);
  const items = purchaseItemsFromScenario(scenario);

  if (!items.length) {
    selectedBookingName.textContent = "Ссылки пока недоступны";
    selectedBookingMeta.textContent = "Корзина откроется, но часть бронирований может быть недоступна.";
    purchaseNote.textContent =
      "Сценарий собран, но ссылки на оформление для этого варианта пока недоступны.";
    extrasGrid.append(
      createOptionCard({
        badge: "INFO",
        title: "Пока без бронирования",
        subtitle: "Ссылки еще не появились",
        price: "—",
        description: "Можно изменить пожелания и попробовать подобрать другой вариант.",
        buttonText: "Нет ссылки",
        theme: "sand",
      })
    );
    return;
  }

  selectedBookingName.textContent = `${items.length} ссылки на Туту`;
  selectedBookingMeta.textContent = items.map((item) => item.title).join(" • ");
  purchaseNote.textContent =
    "Кнопка ниже откроет корзину со всеми доступными ссылками по выбранному сценарию.";

  items.forEach((item) => {
    extrasGrid.append(
      createOptionCard({
        ...item,
        onClick: () => window.open(item.url, "_blank", "noopener"),
      })
    );
  });
}

function renderDetail(scenario) {
  state.currentScenario = scenario;
  detail.classList.remove("hidden");
  refineResult.classList.add("hidden");

  document.querySelector("#detail-mode").textContent = scenario.title;
  document.querySelector("#detail-city").textContent = scenario.destination;
  document.querySelector("#detail-summary").textContent = scenario.tagline;
  document.querySelector("#detail-budget").textContent = formatBudget(scenario.total_price_rub, true);
  document.querySelector("#detail-duration").textContent =
    scenario.duration_label || formatDurationHours(scenario.duration_hours);
  document.querySelector("#detail-transport").textContent = transportSummary(scenario.transport);
  document.querySelector("#detail-score").textContent = `${scenario.score.total} / 100`;

  renderReasons(scenario.reasons);
  renderTimeline(scenario.itinerary || []);
  renderHotel(scenario);
  renderPurchaseOptions(scenario);

  buyButton.disabled = false;
  detail.scrollIntoView({ behavior: "smooth", block: "start" });
}

function updateScenarioInState(updatedScenario) {
  if (!state.result) return;
  state.result.scenarios = state.result.scenarios.map((scenario) =>
    scenario.id === updatedScenario.id ? updatedScenario : scenario
  );
}

async function openScenarioDetail(scenarioId) {
  try {
    const scenario = await fetchJSON(`${API}/escape/${state.escapeId}/scenario/${scenarioId}`);
    renderDetail(scenario);
  } catch (error) {
    statusMain.textContent = error.message || "Не удалось открыть сценарий";
  }
}

function buildPayload() {
  const origin = (promptInputs[0] && promptInputs[0].value.trim()) || "Москва";
  const wishes = promptInputs
    .slice(1)
    .map((input) => input.value.trim())
    .filter(Boolean);

  return {
    origin,
    budget_rub: Number(budgetInput.value),
    duration_hours: Number(durationInput.value) * 24,
    moods: Array.from(state.selectedMoods),
    wishes,
  };
}

async function runSearchFlow(event) {
  event.preventDefault();
  detail.classList.add("hidden");
  refineResult.classList.add("hidden");
  results.classList.add("hidden");

  const timer = startStatusAnimation();
  try {
    const result = await fetchJSON(`${API}/escape`, {
      method: "POST",
      body: buildPayload(),
    });
    state.escapeId = result.id;
    state.result = result;
    window.clearInterval(timer);
    renderStatus(statusMessages.length - 1);
    renderResults(result);
    if (result.scenarios.length) {
      await openScenarioDetail(result.scenarios[0].id);
    }
  } catch (error) {
    window.clearInterval(timer);
    statusMain.textContent = error.message || "Не удалось собрать поездку";
  }
}

function openBasket() {
  if (!state.escapeId || !state.currentScenario) return;
  const params = new URLSearchParams({
    escape_id: state.escapeId,
    scenario_id: state.currentScenario.id,
  });
  window.location.href = `/basket?${params.toString()}`;
}

function buildRefineSummary(refined) {
  if (refined.changes && refined.changes.length) {
    return refined.changes
      .map((change) => `${change.label}: ${change.before} → ${change.after}`)
      .join(" • ");
  }
  if (refined.unmet && refined.unmet.length) {
    return `Не все пожелания удалось выполнить: ${refined.unmet.join(", ")}`;
  }
  return "Маршрут пересобран под новые пожелания.";
}

async function runRefineFlow() {
  if (!state.currentScenario || !state.escapeId) return;
  const note = refineInput.value.trim();
  if (!note) {
    refineSummary.textContent = "Добавь хотя бы одно пожелание для пересборки маршрута.";
    refineResult.classList.remove("hidden");
    return;
  }

  refineButton.disabled = true;
  refineButton.textContent = "ДОПИЛИВАЕМ…";
  try {
    const refined = await fetchJSON(
      `${API}/escape/${state.escapeId}/scenario/${state.currentScenario.id}/refine`,
      {
        method: "POST",
        body: { note },
      }
    );
    updateScenarioInState(refined.scenario);
    renderDetail(refined.scenario);
    refineSummary.textContent = buildRefineSummary(refined);
    refineResult.classList.remove("hidden");
  } catch (error) {
    refineSummary.textContent = error.message || "Не удалось уточнить маршрут.";
    refineResult.classList.remove("hidden");
  } finally {
    refineButton.disabled = false;
    refineButton.textContent = "ДОПИЛИТЬ МАРШРУТ →";
  }
}

async function refreshMcpStatus() {
  try {
    const health = await fetchJSON(`${API}/health`);
    if (health.mcp && health.mcp.available) {
      mcpStatus.textContent = "Данные Туту подключены, можно собирать поездку";
      mcpStatus.dataset.state = "ok";
    } else {
      mcpStatus.textContent = "Источник данных сейчас отвечает нестабильно, часть вариантов может не загрузиться";
      mcpStatus.dataset.state = "warn";
    }
  } catch {
    mcpStatus.textContent = "Не удалось проверить источник данных, но интерфейс готов к поиску";
    mcpStatus.dataset.state = "warn";
  }
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = data && data.error && data.error.message
      ? data.error.message
      : "Что-то пошло не так";
    throw new Error(message);
  }
  return data;
}

async function init() {
  syncRanges();
  budgetInput.addEventListener("input", syncRanges);
  durationInput.addEventListener("input", syncRanges);
  tripForm.addEventListener("submit", runSearchFlow);
  closeDetailButton.addEventListener("click", () => detail.classList.add("hidden"));
  refineButton.addEventListener("click", runRefineFlow);
  buyButton.addEventListener("click", openBasket);

  document.querySelectorAll('a[href="#"]').forEach((link) => {
    link.addEventListener("click", (event) => event.preventDefault());
  });

  try {
    const meta = await fetchJSON(`${API}/meta`);
    renderMoods(meta.moods || defaultMoods());
    if (promptInputs[0] && !promptInputs[0].value.trim()) {
      promptInputs[0].value = meta.default_origin || "Москва";
    }
  } catch {
    renderMoods(defaultMoods());
  }

  refreshMcpStatus();
}

init();
