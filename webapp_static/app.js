const scopeSelect = document.getElementById("scope-select");
const groupSelect = document.getElementById("group-select");
const groupLabel = document.getElementById("group-label");
const yearInput = document.getElementById("year-input");
const presetSelect = document.getElementById("preset-select");
const densitySelect = document.getElementById("density-select");
const statusFilterInputs = [...document.querySelectorAll("input[name='status-filter']")];
const categoryFilterInputs = [...document.querySelectorAll("input[name='category-filter']")];
const searchInput = document.getElementById("search-input");
const subtitle = document.getElementById("subtitle");
const statusLine = document.getElementById("status-line");
const timelineWrap = document.getElementById("timeline-wrap");
const timelineBody = document.getElementById("timeline-body");
const monthsRow = document.getElementById("months-row");
const todayBtn = document.getElementById("today-btn");
const reloadBtn = document.getElementById("reload-btn");
const detailsModal = document.getElementById("details-modal");
const detailsBackdrop = document.getElementById("details-backdrop");
const detailsContent = document.getElementById("details-content");
const detailsCloseBtn = document.getElementById("details-close-btn");

const state = {
  profile: null,
  overlaps: null,
  initData: "",
  devUserId: "",
};

const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "short" });
const ROLE_LABELS = {
  superadmin: "Суперадмин",
  group_admin: "Администратор группы",
  group_viewer: "Наблюдатель группы",
  user: "Сотрудник",
};
const CATEGORY_LABELS = {
  vacation: "Отпуск",
  sick: "Больничный",
  dayoff: "DayOff",
  other: "Другое",
};
const CATEGORY_SHORT_LABELS = {
  vacation: "Отп",
  sick: "Бол",
  dayoff: "DO",
  other: "Дрг",
};
const STATUS_LABELS = {
  pending: "На согласовании",
  approved: "Одобрено",
  declined: "Отклонено",
};

let searchDebounceTimer = null;
let resizeDebounceTimer = null;

function formatLocalIso(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseIsoLocal(value) {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function utcDayIndex(date) {
  return Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / (24 * 60 * 60 * 1000));
}

function daysBetweenDates(start, end) {
  return utcDayIndex(end) - utcDayIndex(start);
}

function todayIso() {
  return formatLocalIso(new Date());
}

function getUserColumnWidth() {
  const css = getComputedStyle(document.documentElement).getPropertyValue("--user-col-w").trim();
  const value = parseFloat(css.replace("px", ""));
  return Number.isFinite(value) && value > 0 ? value : 260;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function resolveScale(totalDays, availableTrackWidth = 0) {
  const isCompact = densitySelect.value === "compact";
  const fitted = availableTrackWidth > 0 ? availableTrackWidth / totalDays : 0;

  if (totalDays <= 45) {
    const base = isCompact ? 20 : 28;
    const min = isCompact ? 14 : 20;
    const max = isCompact ? 64 : 80;
    return {
      headerMode: "day",
      dayWidth: clamp(Math.max(base, fitted || base), min, max),
    };
  }
  if (totalDays <= 120) {
    const base = isCompact ? 7 : 10;
    const min = isCompact ? 5 : 7;
    const max = isCompact ? 20 : 28;
    return {
      headerMode: "week",
      dayWidth: clamp(Math.max(base, fitted || base), min, max),
    };
  }

  const base = isCompact ? 3 : 4;
  const min = isCompact ? 2.2 : 2.8;
  const max = isCompact ? 6 : 8;
  return {
    headerMode: "month",
    dayWidth: clamp(Math.max(base, fitted || base), min, max),
  };
}

function applyRuntimeDayWidth(dayWidth) {
  document.documentElement.style.setProperty("--day-w", `${dayWidth}px`);
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

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
}

function categoryLabel(category) {
  return CATEGORY_LABELS[category] || category;
}

function categoryShortLabel(category) {
  return CATEGORY_SHORT_LABELS[category] || category.slice(0, 3);
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function formatIsoDate(value) {
  if (!value) return "—";
  const parts = value.split("-");
  if (parts.length !== 3) return value;
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

function renderProfile(profile) {
  state.profile = profile;
  const username = profile.user.username ? `@${profile.user.username}` : "без username";
  subtitle.textContent = `${profile.user.fullname} (${username}), роль: ${roleLabel(profile.role)}`;

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
  presetSelect.value = "current_year";
  densitySelect.value = window.matchMedia("(max-width: 900px)").matches ? "compact" : "detailed";
  applyDensity();
  applyPresetState();
  toggleGroupFilter();
}

function toggleGroupFilter() {
  const isGroupScope = scopeSelect.value === "group";
  groupLabel.style.display = isGroupScope ? "flex" : "none";
}

function monthBounds(date) {
  return {
    start: new Date(date.getFullYear(), date.getMonth(), 1),
    end: new Date(date.getFullYear(), date.getMonth() + 1, 0),
  };
}

function weekStartMonday(date) {
  const start = new Date(date);
  const offset = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - offset);
  return new Date(start.getFullYear(), start.getMonth(), start.getDate());
}

function shortDayNumber(date) {
  return String(date.getDate()).padStart(2, "0");
}

function shortDayLabel(date) {
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mm}`;
}

function buildHeaderBlocks(periodStart, periodEnd, dayWidth, headerMode) {
  const start = parseIsoLocal(periodStart);
  const end = parseIsoLocal(periodEnd);
  const blocks = [];

  if (headerMode === "day") {
    let cursor = new Date(start);
    while (cursor <= end) {
      blocks.push({
        label: shortDayNumber(cursor),
        width: dayWidth,
        kind: "day",
      });
      cursor = addDays(cursor, 1);
    }
    return blocks;
  }

  if (headerMode === "week") {
    let cursor = weekStartMonday(start);
    while (cursor <= end) {
      const weekEnd = addDays(cursor, 6);
      const segmentStart = cursor < start ? start : cursor;
      const segmentEnd = weekEnd > end ? end : weekEnd;
      const width = (daysBetweenDates(segmentStart, segmentEnd) + 1) * dayWidth;
      blocks.push({
        label: shortDayLabel(segmentStart),
        width,
        kind: "week",
      });
      cursor = addDays(cursor, 7);
    }
    return blocks;
  }

  let cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  while (cursor <= end) {
    const bounds = monthBounds(cursor);
    const segmentStart = bounds.start < start ? start : bounds.start;
    const segmentEnd = bounds.end > end ? end : bounds.end;
    const width = (daysBetweenDates(segmentStart, segmentEnd) + 1) * dayWidth;
    blocks.push({
      label: monthFormatter.format(segmentStart),
      width,
      kind: "month",
    });
    cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
  }
  return blocks;
}

function buildMonthHeader(periodStart, periodEnd, totalWidth, dayWidth, headerMode) {
  monthsRow.innerHTML = "";
  const inner = document.createElement("div");
  inner.className = "months-inner";
  inner.style.width = `${totalWidth}px`;
  monthsRow.appendChild(inner);

  buildHeaderBlocks(periodStart, periodEnd, dayWidth, headerMode).forEach((segment) => {
    const block = document.createElement("div");
    block.className = `month-block month-block--${segment.kind}`;
    block.style.width = `${segment.width}px`;
    block.textContent = segment.label;
    inner.appendChild(block);
  });

  return inner;
}

function daysBetween(startDate, endDate) {
  return daysBetweenDates(parseIsoLocal(startDate), parseIsoLocal(endDate));
}

function buildTooltip(interval) {
  const comment = interval.comment || "—";
  return `${categoryLabel(interval.category)}\n${formatIsoDate(interval.start_date)} - ${formatIsoDate(interval.end_date)}\n${statusLabel(interval.status)}\nКомментарий: ${comment}`;
}

function formatPeriodForStatus(period) {
  if (!period) return "";
  return `${formatIsoDate(period.start_date)} - ${formatIsoDate(period.end_date)}`;
}

function presetRange() {
  const preset = presetSelect.value;
  const now = new Date();
  if (preset === "current_month") {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    return {
      start: formatLocalIso(start),
      end: formatLocalIso(end),
    };
  }
  if (preset === "next_90_days") {
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const end = new Date(start);
    end.setDate(start.getDate() + 89);
    return {
      start: formatLocalIso(start),
      end: formatLocalIso(end),
    };
  }
  return null;
}

function applyPresetState() {
  const preset = presetSelect.value;
  yearInput.disabled = preset !== "current_year";
}

function applyDensity() {
  document.documentElement.setAttribute("data-density", densitySelect.value);
}

function selectedCheckboxValues(inputs) {
  return inputs.filter((input) => input.checked).map((input) => input.value);
}

function ensureAtLeastOneStatusChecked(changedInput) {
  if (selectedCheckboxValues(statusFilterInputs).length > 0) {
    return true;
  }
  changedInput.checked = true;
  return false;
}

function showDetailsPanel(text) {
  detailsContent.textContent = text;
  detailsModal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function hideDetailsPanel() {
  detailsModal.classList.add("hidden");
  document.body.style.overflow = "";
}

async function openAbsenceDetails(absenceId) {
  showDetailsPanel("Загрузка деталей отсутствия...");
  try {
    const details = await apiGet(`/webapp/v1/absence/${absenceId}`);
    const username = details.user.username ? `@${details.user.username}` : "—";
    const message =
      `Сотрудник: ${details.user.fullname}\n` +
      `Username: ${username}\n` +
      `Категория: ${categoryLabel(details.category)}\n` +
      `Период: ${formatIsoDate(details.start_date)} - ${formatIsoDate(details.end_date)}\n` +
      `Статус: ${statusLabel(details.status)}\n` +
      `Комментарий: ${details.comment || "—"}`;
    showDetailsPanel(message);
  } catch (error) {
    showDetailsPanel(`Ошибка: ${error.message}`);
  }
}

function renderTimeline(overlaps) {
  state.overlaps = overlaps;
  timelineBody.innerHTML = "";
  timelineWrap.classList.remove("hidden");

  const startDate = overlaps.period.start_date;
  const endDate = overlaps.period.end_date;
  const daysTotal = daysBetween(startDate, endDate) + 1;
  const availableTrackWidth = Math.max(0, timelineWrap.clientWidth - getUserColumnWidth() - 2);
  const scale = resolveScale(daysTotal, availableTrackWidth);
  const dayWidth = scale.dayWidth;
  applyRuntimeDayWidth(dayWidth);
  const trackWidth = Math.max(daysTotal * dayWidth, 400);

  const intervalsByUser = new Map();
  overlaps.intervals.forEach((interval) => {
    if (!intervalsByUser.has(interval.user_id)) {
      intervalsByUser.set(interval.user_id, []);
    }
    intervalsByUser.get(interval.user_id).push(interval);
  });

  if (!overlaps.users.length) {
    statusLine.textContent = "Нет данных для выбранного фильтра.";
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "За выбранный период отсутствий не найдено.";
    timelineBody.appendChild(empty);
    monthsRow.innerHTML = "";
    return;
  }

  const monthsInner = buildMonthHeader(startDate, endDate, trackWidth, dayWidth, scale.headerMode);
  statusLine.textContent =
    `Пользователей: ${overlaps.meta.total_users}, интервалов: ${overlaps.meta.total_intervals}. ` +
    `Период: ${formatPeriodForStatus(overlaps.period)}`;

  const todayOffset = daysBetween(startDate, todayIso());
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
      const clippedStart = interval.start_date < startDate ? startDate : interval.start_date;
      const clippedEnd = interval.end_date > endDate ? endDate : interval.end_date;
      if (daysBetween(clippedStart, clippedEnd) < 0) {
        return;
      }

      const offset = Math.max(0, daysBetween(startDate, clippedStart));
      const width = (daysBetween(clippedStart, clippedEnd) + 1) * dayWidth;
      const bar = document.createElement("div");
      bar.className = `bar ${interval.category}`;
      bar.style.left = `${offset * dayWidth}px`;
      bar.style.width = `${Math.max(width, 4)}px`;
      bar.title = buildTooltip(interval);
      const widthPx = Math.max(width, 4);
      if (widthPx < 22) {
        bar.textContent = categoryShortLabel(interval.category).slice(0, 1);
      } else if (widthPx < 48) {
        bar.textContent = categoryShortLabel(interval.category);
      } else {
        bar.textContent = categoryLabel(interval.category);
      }
      bar.addEventListener("click", () => {
        openAbsenceDetails(interval.absence_id);
      });
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
  const selectedStatuses = selectedCheckboxValues(statusFilterInputs);
  const selectedCategories = selectedCheckboxValues(categoryFilterInputs);
  const query = {
    scope_type: scopeSelect.value,
    statuses: selectedStatuses.join(","),
    categories: selectedCategories.join(","),
    q: (searchInput.value || "").trim(),
  };
  const preset = presetSelect.value;
  if (preset === "current_year") {
    query.year = yearInput.value || new Date().getFullYear();
  } else {
    const range = presetRange();
    if (range) {
      query.start_date = range.start;
      query.end_date = range.end;
    }
  }
  if (scopeSelect.value === "group") {
    query.group_id = groupSelect.value;
  }
  return query;
}

function scrollToToday() {
  const marker = timelineBody.querySelector(".today-marker");
  if (!marker) {
    statusLine.textContent = "Маркер «Сегодня» вне выбранного периода.";
    return;
  }
  const targetLeft = Math.max(marker.offsetLeft - 80, 0);
  timelineBody.scrollTo({ left: targetLeft, behavior: "smooth" });
}

async function refreshData() {
  try {
    hideDetailsPanel();
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
presetSelect.addEventListener("change", async () => {
  applyPresetState();
  await refreshData();
});
densitySelect.addEventListener("change", () => {
  applyDensity();
  refreshData();
});
todayBtn.addEventListener("click", scrollToToday);
reloadBtn.addEventListener("click", refreshData);
detailsCloseBtn.addEventListener("click", hideDetailsPanel);
detailsBackdrop.addEventListener("click", hideDetailsPanel);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !detailsModal.classList.contains("hidden")) {
    hideDetailsPanel();
  }
});

statusFilterInputs.forEach((input) => {
  input.addEventListener("change", async () => {
    if (!ensureAtLeastOneStatusChecked(input)) return;
    await refreshData();
  });
});

categoryFilterInputs.forEach((input) => {
  input.addEventListener("change", refreshData);
});

searchInput.addEventListener("input", () => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer);
  }
  searchDebounceTimer = setTimeout(() => {
    refreshData();
  }, 250);
});

window.addEventListener("resize", () => {
  if (!state.overlaps) return;
  if (resizeDebounceTimer) {
    clearTimeout(resizeDebounceTimer);
  }
  resizeDebounceTimer = setTimeout(() => {
    renderTimeline(state.overlaps);
  }, 120);
});

init();
