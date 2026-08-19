const statusMessages = [
  "Нормализуем пожелания",
  "Ищем направления под ваш ритм",
  "Сравниваем транспорт и время в пути",
  "Собираем разные сценарии поездки",
  "Готовим лучший способ уехать на выходные",
];

const scenarios = [
  {
    id: "comfort",
    mode: "Комфортный",
    city: "Ярославль",
    score: 92,
    price: "≈ 11 800 ₽",
    duration: "3 дня",
    transport: "Поезд",
    nights: "2 ночи",
    summary:
      "Спокойный исторический уикенд без сложной логистики: понятный маршрут, прогулки в центре и свободный темп.",
    reasons: [
      "Хорошо совпадает с запросом на историческую атмосферу",
      "Мало организационного стресса и короткий путь",
      "Легко уложить в исходный бюджет",
      "Подходит для зимней короткой поездки",
    ],
    timeline: [
      {
        day: "Пятница",
        events: [
          ["18:40", "Отправление из Москвы на поезде"],
          ["22:55", "Прибытие и заселение рядом с центром"],
        ],
      },
      {
        day: "Суббота",
        events: [
          ["10:00", "Неспешная прогулка по историческому центру"],
          ["13:30", "Обед и свободное время"],
          ["18:00", "Вечер без жесткого тайминга"],
        ],
      },
      {
        day: "Воскресенье",
        events: [
          ["10:30", "Короткий маршрут по набережной"],
          ["16:20", "Обратный поезд в Москву"],
        ],
      },
    ],
    hotels: [
      {
        name: "Royal Hotel Yaroslavl",
        subtitle: "4★, центр и вид на Волгу",
        price: "8 900 ₽",
        description: "Просторные номера, спокойный спа-блок и 10 минут пешком до набережной.",
        image:
          "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Иоанн Васильевич",
        subtitle: "Бутик-отель в историческом квартале",
        price: "7 600 ₽",
        description: "Атмосферный интерьер, удобный выход к центру и хороший вариант для неспешного уикенда.",
        image:
          "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "SK Royal",
        subtitle: "Современный отель рядом с основным маршрутом",
        price: "6 800 ₽",
        description: "Более практичный вариант с хорошим завтраком и быстрым заселением.",
        image:
          "https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=900&q=80",
      },
    ],
    excursions: [
      {
        name: "Прогулка по старому Ярославлю",
        subtitle: "2 часа, пешком",
        price: "1 800 ₽",
        description: "Классический маршрут по храмам, стрелке и тихим улицам с локальным гидом.",
        image:
          "https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Волга и вечерние виды",
        subtitle: "Закатная прогулка",
        price: "2 400 ₽",
        description: "Небольшая экскурсия с акцентом на атмосферу города и лучшие видовые точки.",
        image:
          "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Гастро-маршрут по центру",
        subtitle: "Еда и локальные истории",
        price: "2 900 ₽",
        description: "Формат для тех, кто хочет добавить поездке вкуса и меньше формального музея.",
        image:
          "https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=900&q=80",
      },
    ],
  },
  {
    id: "energy",
    mode: "Насыщенный",
    city: "Казань",
    score: 89,
    price: "≈ 15 400 ₽",
    duration: "3 дня",
    transport: "Ночной поезд",
    nights: "2 ночи",
    summary:
      "Больше впечатлений за то же время: плотный ритм, гастрономия, прогулки и высокий событийный потенциал.",
    reasons: [
      "Максимум впечатлений в формате короткой поездки",
      "Сильный городской вайб и много контента на выходные",
      "Бюджет почти полностью используется, но остается реалистичным",
      "Подходит под настроение «спонтанность + впечатления»",
    ],
    timeline: [
      {
        day: "Пятница",
        events: [
          ["21:15", "Отправление ночным поездом"],
          ["07:40", "Прибытие и быстрый старт дня"],
        ],
      },
      {
        day: "Суббота",
        events: [
          ["09:30", "Завтрак и прогулка по центру"],
          ["13:00", "Маршрут по главным точкам города"],
          ["20:00", "Вечерний гастро-сценарий"],
        ],
      },
      {
        day: "Воскресенье",
        events: [
          ["10:00", "Еще один короткий маршрут по городу"],
          ["18:10", "Обратный поезд"],
        ],
      },
    ],
    hotels: [
      {
        name: "DoubleTree Kazan City Center",
        subtitle: "4★, активный центр",
        price: "11 500 ₽",
        description: "Удобно для плотного графика: быстрое заселение, центр рядом и хороший сервис.",
        image:
          "https://images.unsplash.com/photo-1445019980597-93fa8acb246c?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Отель Ногай",
        subtitle: "Исторический корпус и удобная локация",
        price: "9 800 ₽",
        description: "Хороший баланс цены, стиля и доступа к основным городским точкам.",
        image:
          "https://images.unsplash.com/photo-1455587734955-081b22074882?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Kazanskoe Podvorie",
        subtitle: "Спокойнее, но все еще рядом",
        price: "8 400 ₽",
        description: "Для тех, кто хочет чуть тише ночевку, не теряя городскую динамику.",
        image:
          "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80",
      },
    ],
    excursions: [
      {
        name: "Кремль и Старо-Татарская слобода",
        subtitle: "Хит-маршрут на полдня",
        price: "2 200 ₽",
        description: "Классическая экскурсия по главным местам, если хочется быстро собрать основу города.",
        image:
          "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Вечерняя гастро-прогулка",
        subtitle: "Дегустации и локальный контекст",
        price: "3 400 ₽",
        description: "Насыщенный формат для тех, кто едет за едой, вайбом и историей без скучной подачи.",
        image:
          "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Свияжск одним днем",
        subtitle: "Выездная экскурсия",
        price: "4 900 ₽",
        description: "Более содержательный вариант, если хочется добавить сильное отдельное впечатление.",
        image:
          "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=900&q=80",
      },
    ],
  },
  {
    id: "unexpected",
    mode: "Неочевидный",
    city: "Переславль-Залесский",
    score: 94,
    price: "≈ 13 600 ₽",
    duration: "3 дня",
    transport: "Поезд + короткий трансфер",
    nights: "2 ночи",
    summary:
      "Менее очевидный, но очень убедительный вариант: ближе, тише и атмосфернее, чем ожидаешь от зимнего уикенда.",
    reasons: [
      "Сохраняет исторический запрос, но предлагает менее избитое направление",
      "Дает ощущение смены обстановки без дорогой логистики",
      "Лучше балансирует бюджет, уют и короткий тайминг",
      "Подходит для красивого refine-сценария в демо",
    ],
    timeline: [
      {
        day: "Пятница",
        events: [
          ["17:50", "Выезд из Москвы"],
          ["21:20", "Прибытие и заселение в центре"],
        ],
      },
      {
        day: "Суббота",
        events: [
          ["10:00", "Исторический маршрут и зимняя прогулка"],
          ["14:00", "Свободное время, кафе и видовые точки"],
          ["19:30", "Спокойный вечер в центре"],
        ],
      },
      {
        day: "Воскресенье",
        events: [
          ["11:00", "Поздний завтрак и еще немного города"],
          ["16:45", "Обратная дорога"],
        ],
      },
    ],
    hotels: [
      {
        name: "AZIMUT Отель Переславль",
        subtitle: "Загородный формат с spa",
        price: "10 900 ₽",
        description: "Более выразительный вариант для красивого уикенда с ощущением настоящего отдыха.",
        image:
          "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Victoria Plaza",
        subtitle: "Номер с видом на озеро",
        price: "8 100 ₽",
        description: "Уютный вариант ближе к прогулкам и вечерней тишине, без перегруза по бюджету.",
        image:
          "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Лесная сказка",
        subtitle: "Тихий отель для спокойной поездки",
        price: "6 900 ₽",
        description: "Максимум уюта и меньше суеты, если хочется замедлиться и не гнаться за вау-сервисом.",
        image:
          "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80",
      },
    ],
    excursions: [
      {
        name: "Пеший маршрут по старому Переславлю",
        subtitle: "История и камерный ритм",
        price: "1 600 ₽",
        description: "Неспешная экскурсия по центру с акцентом на атмосферу и локальные легенды.",
        image:
          "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Плещеево озеро и видовые точки",
        subtitle: "Природа рядом с городом",
        price: "2 300 ₽",
        description: "Хороший способ сделать поездку визуально богаче и добавить воздуха в маршрут.",
        image:
          "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=900&q=80",
      },
      {
        name: "Музеи без спешки",
        subtitle: "Небольшой культурный сет",
        price: "2 700 ₽",
        description: "Подойдет, если хочется более собранного культурного сценария без длинных переездов.",
        image:
          "https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?auto=format&fit=crop&w=900&q=80",
      },
    ],
  },
];

const budgetInput = document.querySelector("#budget");
const durationInput = document.querySelector("#duration");
const budgetValue = document.querySelector("#budget-value");
const durationValue = document.querySelector("#duration-value");
const moodGrid = document.querySelector("#mood-grid");
const tripForm = document.querySelector("#trip-form");
const statusBoard = document.querySelector("#status-board");
const statusMain = document.querySelector("#status-main");
const statusSteps = document.querySelector("#status-steps");
const results = document.querySelector("#results");
const scenarioGrid = document.querySelector("#scenario-grid");
const detail = document.querySelector("#detail");
const closeDetailButton = document.querySelector("#close-detail");
const refineButton = document.querySelector("#refine-button");
const refineResult = document.querySelector("#refine-result");
const refineSummary = document.querySelector("#refine-summary");
const hotelGrid = document.querySelector("#hotel-grid");
const excursionGrid = document.querySelector("#excursion-grid");
const selectedHotelName = document.querySelector("#selected-hotel-name");
const selectedHotelMeta = document.querySelector("#selected-hotel-meta");
const selectedExcursionName = document.querySelector("#selected-excursion-name");
const selectedExcursionMeta = document.querySelector("#selected-excursion-meta");
const scenarioTemplate = document.querySelector("#scenario-template");
const optionTemplate = document.querySelector("#option-template");

let activeScenario = scenarios[2];
let selectedHotel = activeScenario.hotels[0];
let selectedExcursion = activeScenario.excursions[0];

function formatBudget(value) {
  return `${Number(value).toLocaleString("ru-RU")} ₽`;
}

function formatDuration(days) {
  if (days === 1) return "1 день";
  if (days < 5) return `${days} дня`;
  return `${days} дней`;
}

function renderRanges() {
  budgetValue.textContent = formatBudget(budgetInput.value);
  durationValue.textContent = formatDuration(Number(durationInput.value));
}

function toggleMood(event) {
  const button = event.target.closest(".mood-chip");
  if (!button) return;
  button.classList.toggle("selected");
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

function populateScenarios() {
  scenarioGrid.innerHTML = "";

  scenarios.forEach((scenario) => {
    const node = scenarioTemplate.content.cloneNode(true);
    node.querySelector(".scenario-mode").textContent = scenario.mode;
    node.querySelector(".scenario-city").textContent = scenario.city;
    node.querySelector(".scenario-score").textContent = `${scenario.score} / 100`;
    node.querySelector(".scenario-copy").textContent = scenario.summary;

    const meta = node.querySelector(".scenario-meta");
    [scenario.price, scenario.duration, scenario.transport, scenario.nights].forEach((item) => {
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
      activeScenario = scenario;
      selectedHotel = scenario.hotels[0];
      selectedExcursion = scenario.excursions[0];
      renderDetail(scenario);
      detail.classList.remove("hidden");
      detail.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    scenarioGrid.append(node);
  });
}

function renderReasons(scenario) {
  const reasons = document.querySelector("#reason-list");
  reasons.innerHTML = "";
  scenario.reasons.forEach((reason) => {
    const li = document.createElement("li");
    li.textContent = reason;
    reasons.append(li);
  });
}

function renderTimeline(scenario) {
  const timeline = document.querySelector("#timeline");
  timeline.innerHTML = "";

  scenario.timeline.forEach((day) => {
    const card = document.createElement("article");
    card.className = "timeline-day";

    const title = document.createElement("h4");
    title.textContent = day.day;
    card.append(title);

    day.events.forEach(([time, text]) => {
      const event = document.createElement("div");
      event.className = "timeline-event";

      const timeNode = document.createElement("time");
      timeNode.textContent = time;

      const textNode = document.createElement("div");
      textNode.textContent = text;

      event.append(timeNode, textNode);
      card.append(event);
    });

    timeline.append(card);
  });
}

function renderSelectedSummary() {
  selectedHotelName.textContent = selectedHotel.name;
  selectedHotelMeta.textContent = `${selectedHotel.price} • ${selectedHotel.subtitle}`;
  selectedExcursionName.textContent = selectedExcursion.name;
  selectedExcursionMeta.textContent = `${selectedExcursion.price} • ${selectedExcursion.subtitle}`;
}

function createOptionCard(option, type) {
  const node = optionTemplate.content.cloneNode(true);
  const card = node.querySelector(".option-card");
  const media = node.querySelector(".option-media");
  const title = node.querySelector(".option-title");
  const subtitle = node.querySelector(".option-subtitle");
  const price = node.querySelector(".option-price");
  const copy = node.querySelector(".option-copy");
  const button = node.querySelector(".option-button");

  card.dataset.type = type;
  card.dataset.name = option.name;
  media.style.backgroundImage = `linear-gradient(180deg, rgba(18, 16, 74, 0.06), rgba(18, 16, 74, 0.38)), url("${option.image}")`;
  title.textContent = option.name;
  subtitle.textContent = option.subtitle;
  price.textContent = option.price;
  copy.textContent = option.description;

  const isSelected =
    type === "hotel" ? selectedHotel.name === option.name : selectedExcursion.name === option.name;

  if (isSelected) {
    card.classList.add("selected");
    button.textContent = "Выбрано";
  }

  button.addEventListener("click", () => {
    if (type === "hotel") {
      selectedHotel = option;
      renderOptions(activeScenario.hotels, hotelGrid, "hotel");
    } else {
      selectedExcursion = option;
      renderOptions(activeScenario.excursions, excursionGrid, "excursion");
    }

    renderSelectedSummary();
  });

  return node;
}

function renderOptions(options, container, type) {
  container.innerHTML = "";
  options.forEach((option) => {
    container.append(createOptionCard(option, type));
  });
}

function renderDetail(scenario) {
  document.querySelector("#detail-mode").textContent = scenario.mode;
  document.querySelector("#detail-city").textContent = scenario.city;
  document.querySelector("#detail-summary").textContent = scenario.summary;
  document.querySelector("#detail-budget").textContent = scenario.price;
  document.querySelector("#detail-duration").textContent = scenario.duration;
  document.querySelector("#detail-transport").textContent = scenario.transport;
  document.querySelector("#detail-score").textContent = `${scenario.score} / 100`;

  renderReasons(scenario);
  renderTimeline(scenario);
  renderOptions(scenario.hotels, hotelGrid, "hotel");
  renderOptions(scenario.excursions, excursionGrid, "excursion");
  renderSelectedSummary();
}

function showResults() {
  results.classList.remove("hidden");
  populateScenarios();
  renderDetail(activeScenario);
}

async function runSearchFlow(event) {
  event.preventDefault();
  detail.classList.add("hidden");
  refineResult.classList.add("hidden");
  statusBoard.classList.remove("hidden");
  results.classList.add("hidden");
  renderStatus(0);
  statusBoard.scrollIntoView({ behavior: "smooth", block: "start" });

  for (let index = 1; index < statusMessages.length; index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 700));
    renderStatus(index);
  }

  await new Promise((resolve) => window.setTimeout(resolve, 450));
  showResults();
}

function runRefineFlow() {
  const refinedPrice = budgetInput.value >= 17000 ? "≈ 16 900 ₽" : "≈ 15 900 ₽";
  refineSummary.textContent =
    `Обновили сценарий "${activeScenario.mode.toLowerCase()}": выбрали ${selectedHotel.name}, ` +
    `добавили "${selectedExcursion.name}" и сохранили поездку в пределах ${refinedPrice}.`;
  refineResult.classList.remove("hidden");
}

budgetInput.addEventListener("input", renderRanges);
durationInput.addEventListener("input", renderRanges);
moodGrid.addEventListener("click", toggleMood);
tripForm.addEventListener("submit", runSearchFlow);
closeDetailButton.addEventListener("click", () => detail.classList.add("hidden"));
refineButton.addEventListener("click", runRefineFlow);

renderRanges();
