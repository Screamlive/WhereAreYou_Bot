const scopeSelect = document.getElementById("scope-select");
const groupSelect = document.getElementById("group-select");
const groupLabel = document.getElementById("group-label");
const yearInput = document.getElementById("year-input");
const subtitle = document.getElementById("subtitle");
const statusLine = document.getElementById("status-line");
const timelineWrap = document.getElementById("timeline-wrap");
const timelineBody = document.getElementById("timeline-body");
const monthsRow = document.getElementById("months-row");
const reloadBtn = document.getElementById("reload-btn");

const state = {
  profile: null,
  overlaps: null,
  initData: "",
  devUserId: "",
};

const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "short" });

function getDayWidth() {
  const css = getComputedStyle(document.documentElement).getPropertyValue("--day-w").trim();
  const value = parseFloat(css.replace("px", ""));
  return Number.isFinite(value) && value > 0 ? value : 3;
}

function formatError(text) {
  if (!text) return "Ошибка запроса.";
  try {
    const payload = JSON.parse(text);
    if (payload && payload.error) return payload.error;
  } catch (_err) {
    return text;
  }
  return text;
}

async function apiGet(path, query = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });

  if (state.initData) {
    url.searchParams.set("init_data", state.initData);
  }

  const headers = {};
  if (!state.initData && state.devUserId) {
    headers["X-Telegram-User-Id"] = state.devUserId;
  }

  const response = await fetch(url.toString(), { headers });
  const body = await response.text();
  if (!response.ok) {
    throw new Error(formatError(body));
  }
  return JSON.parse(body);
}

function detectTelegramContext() {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (!tg) return;
  tg.ready();
  tg.expand();
  state.initData = tg.initData || "";
}

function readDevQueryParams() {
  const url = new URL(window.location.href);
  state.devUserId = url.searchParams.get("dev_user_id") || "";
}

function scopeLabel(scopeType) {
  if (scopeType === "global") return "Глобально";
  if (scopeType === "group") return "Группа";
  if (scopeType === "superadmins") return "Суперадмины";
  return scopeType;
}

function renderProfile(profile) {
  state.profile = profile;
  const username = profile.user.username ? `@${profile.user.username}` : "без username";
  subtitle.textContent = `${profile.user.fullname} (${username}), роль: ${profile.role}`;

  scopeSelect.innerHTML = "";
  profile.scopes.forEach((scopeType) => {
    const option = document.createElement("option");
    option.value = scopeType;
    option.textContent = scopeLabel(scopeType);
    scopeSelect.appendChild(option);
  });
  scopeSelect.value = profile.default_scope.type;

  groupSelect.innerHTML = "";
  profile.groups.forEach((group) => {
    const option = document.createElement("option");
    option.value = String(group.id);
    option.textContent = group.name;
    groupSelect.appendChild(option);
  });

  const defaultGroupId = profile.default_scope.group_id;
  if (defaultGroupId) {
    groupSelect.value = String(defaultGroupId);
  }

  const currentYear = new Date().getFullYear();
  yearInput.value = String(currentYear);
  toggleGroupFilter();
}

function toggleGroupFilter() {
  const isGroupScope = scopeSelect.value === "group";
  groupLabel.style.display = isGroupScope ? "flex" : "none";
}

function monthSegments(year, dayWidth) {
  const segments = [];
  for (let month = 0; month < 12; month += 1) {
    const start = new Date(year, month, 1);
    const end = new Date(year, month + 1, 0);
    const days = end.getDate();
    segments.push({
      key: `${year}-${month + 1}`,
      label: monthFormatter.format(start),
      width: days * dayWidth,
    });
  }
  return segments;
}

function buildMonthHeader(periodStart, periodEnd, totalWidth, dayWidth) {
  monthsRow.innerHTML = "";
  const inner = document.createElement("div");
  inner.className = "months-inner";
  inner.style.width = `${totalWidth}px`;
  monthsRow.appendChild(inner);

  const start = new Date(periodStart);
  const end = new Date(periodEnd);
  const year = start.getFullYear();
  if (year !== end.getFullYear()) return inner;

  monthSegments(year, dayWidth).forEach((segment) => {
    const block = document.createElement("div");
    block.className = "month-block";
    block.style.width = `${segment.width}px`;
    block.textContent = segment.label;
    inner.appendChild(block);
  });

  return inner;
}

function daysBetween(startDate, endDate) {
  const dayMs = 24 * 60 * 60 * 1000;
  const start = new Date(startDate);
  const end = new Date(endDate);
  return Math.floor((end - start) / dayMs);
}

function buildTooltip(interval) {
  const categoryMap = {
    vacation: "Отпуск",
    sick: "Больничный",
    dayoff: "DayOff",
    other: "Другое",
  };
  const comment = interval.comment || "—";
  return `${categoryMap[interval.category] || interval.category}\n${interval.start_date} - ${interval.end_date}\n${interval.status}\n${comment}`;
}

function renderTimeline(overlaps) {
  state.overlaps = overlaps;
  timelineBody.innerHTML = "";

  const startDate = overlaps.period.start_date;
  const endDate = overlaps.period.end_date;
  const dayWidth = getDayWidth();
  const daysTotal = daysBetween(startDate, endDate) + 1;
  const trackWidth = Math.max(daysTotal * dayWidth, 400);

  const intervalsByUser = new Map();
  overlaps.intervals.forEach((interval) => {
    if (!intervalsByUser.has(interval.user_id)) {
      intervalsByUser.set(interval.user_id, []);
    }
    intervalsByUser.get(interval.user_id).push(interval);
  });

  if (!overlaps.users.length) {
    timelineWrap.classList.remove("hidden");
    statusLine.textContent = "Нет данных для выбранного фильтра.";
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "За выбранный период отсутствий не найдено.";
    timelineBody.appendChild(empty);
    monthsRow.innerHTML = "";
    return;
  }

  const monthsInner = buildMonthHeader(startDate, endDate, trackWidth, dayWidth);
  timelineWrap.classList.remove("hidden");
  statusLine.textContent = `Пользователей: ${overlaps.meta.total_users}, интервалов: ${overlaps.meta.total_intervals}`;

  const todayIso = new Date().toISOString().slice(0, 10);
  const todayOffset = daysBetween(startDate, todayIso);
  const todayInRange = todayOffset >= 0 && todayOffset < daysTotal;

  overlaps.users.forEach((user) => {
    const row = document.createElement("div");
    row.className = "timeline-row";

    const left = document.createElement("div");
    left.className = "user-cell sticky";
    const name = document.createElement("div");
    name.className = "user-name";
    name.textContent = user.fullname;
    const meta = document.createElement("div");
    meta.className = "user-meta";
    meta.textContent = user.username ? `@${user.username}` : `ID ${user.user_id}`;
    left.appendChild(name);
    left.appendChild(meta);

    const track = document.createElement("div");
    track.className = "track";
    track.style.width = `${trackWidth}px`;
    track.style.minWidth = `${trackWidth}px`;

    if (todayInRange) {
      const todayMarker = document.createElement("div");
      todayMarker.className = "today-marker";
      todayMarker.style.left = `${todayOffset * dayWidth}px`;
      track.appendChild(todayMarker);
    }

    const intervals = intervalsByUser.get(user.user_id) || [];
    intervals.forEach((interval) => {
      const offset = Math.max(0, daysBetween(startDate, interval.start_date));
      const width = (daysBetween(interval.start_date, interval.end_date) + 1) * dayWidth;
      const bar = document.createElement("div");
      bar.className = `bar ${interval.category}`;
      bar.style.left = `${offset * dayWidth}px`;
      bar.style.width = `${Math.max(width, 4)}px`;
      bar.title = buildTooltip(interval);
      bar.textContent = interval.category;
      track.appendChild(bar);
    });

    row.appendChild(left);
    row.appendChild(track);
    timelineBody.appendChild(row);
  });

  timelineBody.onscroll = () => {
    monthsInner.style.transform = `translateX(${-timelineBody.scrollLeft}px)`;
  };
}

function currentScopeQuery() {
  const query = {
    scope_type: scopeSelect.value,
    year: yearInput.value || new Date().getFullYear(),
  };
  if (scopeSelect.value === "group") {
    query.group_id = groupSelect.value;
  }
  return query;
}

async function refreshData() {
  try {
    statusLine.textContent = "Загрузка данных...";
    const overlaps = await apiGet("/webapp/v1/overlaps", currentScopeQuery());
    renderTimeline(overlaps);
  } catch (error) {
    timelineWrap.classList.add("hidden");
    statusLine.textContent = `Ошибка: ${error.message}`;
  }
}

async function init() {
  detectTelegramContext();
  readDevQueryParams();

  try {
    const profile = await apiGet("/webapp/v1/me");
    renderProfile(profile);
    await refreshData();
  } catch (error) {
    timelineWrap.classList.add("hidden");
    statusLine.textContent = `Ошибка: ${error.message}`;
    subtitle.textContent = "Не удалось загрузить профиль.";
  }
}

scopeSelect.addEventListener("change", async () => {
  toggleGroupFilter();
  await refreshData();
});

groupSelect.addEventListener("change", refreshData);
yearInput.addEventListener("change", refreshData);
reloadBtn.addEventListener("click", refreshData);

init();
