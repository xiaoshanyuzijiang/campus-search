const BADGE_BASE = "https://raw.githubusercontent.com/863379105/BadgeSpider/64b499a558c397ca1488ec6bb5d727800040bbd4/Badges/";
const normalizeBadgeName = (name) => name.normalize("NFKC").replace(/\s+/g, "").toLocaleLowerCase();
const badgeFiles = new Map(window.schoolBadgeNames.map((name) => [normalizeBadgeName(name), name]));
const badgeUrl = (name) => {
  const file = badgeFiles.get(normalizeBadgeName(name));
  return file ? BADGE_BASE + encodeURIComponent(file + ".jpg") : null;
};

const featuredSchools = [
  { cn: "清华大学", en: "Tsinghua University", abbr: "THU", mark: "清", color: "#75449b", soft: "#f5eff9", url: "https://www.tsinghua.edu.cn" },
  { cn: "北京大学", en: "Peking University", abbr: "PKU", mark: "北", color: "#9c3446", soft: "#fcf2f3", url: "https://www.pku.edu.cn" },
  { cn: "复旦大学", en: "Fudan University", abbr: "FDU", mark: "复", color: "#26639d", soft: "#eff6fd", url: "https://www.fudan.edu.cn" },
  { cn: "上海交通大学", en: "Shanghai Jiao Tong University", abbr: "SJTU", mark: "交", color: "#a03938", soft: "#fcf2f1", url: "https://www.sjtu.edu.cn" },
  { cn: "浙江大学", en: "Zhejiang University", abbr: "ZJU", mark: "浙", color: "#27659f", soft: "#eff6fc", url: "https://www.zju.edu.cn" },
  { cn: "南京大学", en: "Nanjing University", abbr: "NJU", mark: "南", color: "#723f9a", soft: "#f5f0fa", url: "https://www.nju.edu.cn" },
  { cn: "中国科学技术大学", en: "University of Science and Technology of China", abbr: "USTC", mark: "科", color: "#387274", soft: "#edf8f6", url: "https://www.ustc.edu.cn" },
  { cn: "武汉大学", en: "Wuhan University", abbr: "WHU", mark: "武", color: "#4675a1", soft: "#f0f6fb", url: "https://www.whu.edu.cn" },
  { cn: "山西大学", en: "Shanxi University", abbr: "SXU", mark: "山", color: "#078d94", soft: "#edf9f9", url: "https://www.sxu.edu.cn" }
];
const featuredNames = new Set(featuredSchools.map((school) => school.cn));
const schools = featuredSchools.concat(window.schoolBadgeNames
  .filter((name) => !featuredNames.has(name))
  .map((cn) => ({ cn, en: "", abbr: "", mark: cn.slice(0, 1), color: "#3974b9", soft: "#eff6ff", url: "" })));

const byId = (id) => document.getElementById(id);
const search = byId("school-search");
const options = byId("school-options");
const quickPicks = byId("quick-picks-list");
const website = byId("school-url");
const identityCard = byId("identity-card");
const emblem = byId("school-emblem");
const emblemImage = byId("emblem-image");
const resultsSection = byId("results");
const submitButton = byId("submit-button");
const stopButton = byId("stop-button");
document.querySelector(".shortcut").textContent =
  /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ K" : "Ctrl K";
let selectedSchool = null;
let visibleSchools = [];
let activeIndex = -1;
let activeEmblemKey = "";
let researchRequest = null;
let currentResult = null;
const badgeThemes = new Map();

function applyIdentityTheme(school) {
  const theme = badgeThemes.get(normalizeBadgeName(school.cn)) || school;
  identityCard.style.setProperty("--school-color", theme.color);
  identityCard.style.setProperty("--school-soft", theme.soft);
  identityCard.style.setProperty("--school-border", theme.border || theme.color + "29");
}

function updateEmblem(school) {
  const key = normalizeBadgeName(school.cn);
  if (key === activeEmblemKey) return;
  activeEmblemKey = key;
  emblemImage.onload = null;
  emblemImage.onerror = null;
  emblemImage.removeAttribute("src");
  emblemImage.hidden = true;
  emblem.classList.remove("has-image");
  emblem.classList.toggle("is-shield", school.abbr === "NJU");
  byId("emblem-character").hidden = false;
  byId("emblem-code").hidden = false;
  const url = badgeUrl(school.cn);
  if (!url) return;
  emblemImage.onload = () => {
    if (activeEmblemKey !== key) return;
    emblemImage.hidden = false;
    emblem.classList.add("has-image");
    byId("emblem-character").hidden = true;
    byId("emblem-code").hidden = true;
    try {
      const theme = window.schoolBadgeTheme.fromImage(emblemImage);
      if (theme) {
        badgeThemes.set(key, theme);
        applyIdentityTheme(currentSchool());
      }
    } catch {
      // A blocked canvas read must not hide an otherwise valid badge.
    }
  };
  emblemImage.onerror = () => {
    if (activeEmblemKey !== key) return;
    emblemImage.hidden = true;
    emblem.classList.remove("has-image");
  };
  emblemImage.src = url;
}

function makeEmblem(school, small) {
  const emblem = document.createElement("span");
  emblem.className = small ? "mini-emblem" : "school-emblem";
  emblem.classList.toggle("is-shield", school.abbr === "NJU");
  emblem.style.setProperty("--school-color", school.color);
  if (small) {
    const url = badgeUrl(school.cn);
    if (url) {
      const image = document.createElement("img");
      image.crossOrigin = "anonymous";
      image.src = url;
      image.alt = "";
      image.onerror = () => {
        image.remove();
        emblem.classList.remove("has-image");
        emblem.textContent = school.mark;
      };
      emblem.classList.add("has-image");
      emblem.append(image);
    } else {
      emblem.textContent = school.mark;
    }
  } else {
    const character = document.createElement("span");
    character.textContent = school.mark;
    const code = document.createElement("small");
    code.textContent = school.abbr || "SCHOOL";
    emblem.append(character, code);
  }
  return emblem;
}

function currentSchool() {
  if (selectedSchool) return selectedSchool;
  const name = search.value.trim();
  return {
    cn: name,
    mark: name.slice(0, 1) || "校",
    color: "#3974b9",
    soft: "#eff6ff",
    url: website.value.trim()
  };
}

function renderIdentity() {
  const school = currentSchool();
  applyIdentityTheme(school);
  byId("emblem-character").textContent = school.mark;
  byId("emblem-code").textContent = school.abbr || "SCHOOL";
  byId("identity-cn").textContent = school.cn || "请选择学校";
  updateEmblem(school);
  document.querySelectorAll(".quick-pick").forEach((button) => {
    button.classList.toggle("is-selected", button.dataset.abbr === school.abbr && Boolean(selectedSchool));
  });
}

function closeOptions() {
  options.hidden = true;
  search.setAttribute("aria-expanded", "false");
  search.removeAttribute("aria-activedescendant");
  activeIndex = -1;
}

function setActive(index) {
  activeIndex = index;
  Array.from(options.children).forEach((item, itemIndex) => {
    item.classList.toggle("is-active", itemIndex === index);
  });
  if (index >= 0) {
    search.setAttribute("aria-activedescendant", "school-option-" + index);
    options.children[index].scrollIntoView({ block: "nearest" });
  } else {
    search.removeAttribute("aria-activedescendant");
  }
}

function selectSchool(school) {
  selectedSchool = school;
  search.value = school.cn;
  website.value = school.url;
  byId("school-field").classList.remove("has-error");
  byId("school-error").hidden = true;
  renderIdentity();
  closeOptions();
}

function renderOptions() {
  const term = normalizeBadgeName(search.value.trim());
  visibleSchools = (term ? schools.filter((school) => {
    const text = normalizeBadgeName([school.cn, school.en, school.abbr].join(" "));
    return text.includes(term);
  }) : featuredSchools).slice(0, 20);
  options.replaceChildren();
  if (visibleSchools.length === 0) {
    const message = document.createElement("div");
    message.className = "no-options";
    message.textContent = "校徽库中未找到该校；仍可填写学校名称继续检索通知。";
    options.append(message);
  } else {
    visibleSchools.forEach((school, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.id = "school-option-" + index;
      button.className = "school-option";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(selectedSchool === school));
      const copy = document.createElement("span");
      copy.className = "option-copy";
      const name = document.createElement("strong");
      name.textContent = school.cn;
      const english = document.createElement("small");
      english.textContent = school.en;
      const abbr = document.createElement("span");
      abbr.className = "option-abbr";
      abbr.textContent = school.abbr;
      copy.append(name);
      if (school.en) copy.append(english);
      button.append(makeEmblem(school, true), copy, abbr);
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => selectSchool(school));
      options.append(button);
    });
  }
  options.hidden = false;
  search.setAttribute("aria-expanded", "true");
  setActive(-1);
}

schools.slice(0, 4).forEach((school) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "quick-pick";
  button.dataset.abbr = school.abbr;
  button.textContent = school.cn;
  button.addEventListener("click", () => selectSchool(school));
  quickPicks.append(button);
});

search.addEventListener("focus", renderOptions);
search.addEventListener("input", () => {
  const term = search.value.trim().toLocaleLowerCase();
  const exact = schools.find((school) =>
    [school.cn, school.en, school.abbr].some((value) => value.toLocaleLowerCase() === term)
  );
  selectedSchool = exact || null;
  if (!exact) website.value = "";
  if (exact) website.value = exact.url;
  byId("school-field").classList.remove("has-error");
  byId("school-error").hidden = true;
  renderIdentity();
  renderOptions();
});
search.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeOptions();
    return;
  }
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (options.hidden) renderOptions();
    if (visibleSchools.length) {
      const next = event.key === "ArrowDown"
        ? (activeIndex + 1) % visibleSchools.length
        : (activeIndex - 1 + visibleSchools.length) % visibleSchools.length;
      setActive(next);
    }
  }
  if (event.key === "Enter" && !options.hidden && activeIndex >= 0) {
    event.preventDefault();
    selectSchool(visibleSchools[activeIndex]);
  }
});
document.addEventListener("pointerdown", (event) => {
  if (!byId("school-field").contains(event.target)) closeOptions();
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    search.focus();
  }
});
website.addEventListener("input", renderIdentity);
function renderResults(data) {
  currentResult = data;
  const notices = Array.isArray(data.notices) ? data.notices : [];
  byId("results-title").textContent = data.school.name + " · 检索结果";
  byId("results-meta").textContent = "已检索 " + (data.queries?.length || 0) + " 组关键词 · " + (data.files?.length || 0) + " 份相关文件";
  byId("summary-text").textContent = data.summary || "暂无摘要";
  byId("source-count").textContent = notices.length + " 条来源";
  const list = byId("notice-list");
  list.replaceChildren();
  notices.forEach((notice) => {
    const item = document.createElement("li");
    item.className = "notice-card";
    const top = document.createElement("div");
    top.className = "notice-card-top";
    const number = document.createElement("span");
    number.className = "notice-number";
    number.textContent = notice.number;
    const title = document.createElement("h4");
    title.textContent = notice.title;
    top.append(number, title);
    const excerpt = document.createElement("p");
    excerpt.textContent = notice.content || "原文摘要不可用，请打开来源查看。";
    const link = document.createElement("a");
    link.href = notice.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "查看原文 · " + new URL(notice.url).hostname;
    item.append(top, excerpt, link);
    list.append(item);
  });
  byId("result-content").hidden = false;
  renderFiles(data.files || []);
  const steps = byId("step-list");
  steps.replaceChildren();
  (data.steps || []).forEach((step) => {
    const item = document.createElement("li");
    item.textContent = step.tool === "search_notices" ? "检索：" + step.detail : step.detail;
    steps.append(item);
  });
  byId("research-steps").hidden = !steps.children.length;
  byId("export-pdf").disabled = false;
  byId("export-markdown").disabled = false;
}

function renderFiles(files) {
  byId("files-section").hidden = !files.length;
  byId("file-count").textContent = files.length + " 份文件 · 点击下载原文件";
  const list = byId("file-list");
  list.replaceChildren();
  files.forEach((file) => {
    const card = document.createElement("li");
    card.className = "file-card";
    const title = document.createElement("h4");
    title.textContent = "[" + file.number + "] " + file.title;
    const meta = document.createElement("p");
    meta.className = "file-meta";
    meta.textContent = file.filename + " · " + file.status;
    const excerpt = document.createElement("p");
    excerpt.className = "file-excerpt";
    excerpt.textContent = file.content || "";
    excerpt.hidden = !file.content;
    const actions = document.createElement("div");
    actions.className = "file-actions";
    const download = document.createElement("button");
    download.type = "button";
    download.className = "file-download";
    download.textContent = "下载原文件";
    download.disabled = !file.download_url?.startsWith("/api/files/download?");
    download.addEventListener("click", () => downloadFile(file.download_url, {}, file.filename, download));
    const original = document.createElement("a");
    original.href = file.url;
    original.target = "_blank";
    original.rel = "noopener noreferrer";
    original.textContent = "查看原始链接";
    actions.append(download, original);
    card.append(title, meta, excerpt, actions);
    list.append(card);
  });
}

async function downloadFile(url, request, filename, button) {
  const label = button.querySelector("span") || button;
  const previous = label.textContent;
  button.disabled = true;
  label.textContent = "准备中…";
  byId("download-error").hidden = true;
  try {
    const response = await fetch(url, request);
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.detail?.message || "下载失败，请稍后重试。");
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (encoded) filename = decodeURIComponent(encoded[1]);
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename.replace(/[\\/:*?"<>|]/g, "_");
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
  } catch (error) {
    byId("download-error").textContent = error.message || "下载失败，请稍后重试。";
    byId("download-error").hidden = false;
  } finally {
    label.textContent = previous;
    button.disabled = button.classList.contains("export-button") && !currentResult;
  }
}

for (const format of ["pdf", "markdown"]) {
  byId("export-" + format).addEventListener("click", () => {
    if (!currentResult) return;
    const filename = currentResult.school.name + (format === "pdf" ? "-通知摘要.pdf" : "-检索结果.md");
    downloadFile("/api/export/" + format, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentResult)
    }, filename, byId("export-" + format));
  });
}

stopButton.addEventListener("click", () => {
  if (!researchRequest) return;
  const request = researchRequest;
  researchRequest = null;
  request.abort();
  byId("results-title").textContent = "已停止检索";
  byId("results-meta").textContent = "可修改条件后重新检索";
  byId("run-state-text").textContent = "检索已停止。";
  byId("run-state").classList.add("is-stopped");
  stopButton.disabled = true;
  submitButton.disabled = false;
  submitButton.firstChild.textContent = "开始检索 ";
});

byId("notice-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (researchRequest) return;
  if (!search.value.trim()) {
    byId("school-field").classList.add("has-error");
    byId("school-error").hidden = false;
    search.focus();
    return;
  }
  closeOptions();
  const school = currentSchool();
  resultsSection.hidden = false;
  currentResult = null;
  byId("export-pdf").disabled = true;
  byId("export-markdown").disabled = true;
  byId("download-error").hidden = true;
  byId("result-content").hidden = true;
  byId("result-error").hidden = true;
  byId("run-state").hidden = false;
  byId("run-state").classList.remove("is-stopped");
  byId("run-state-text").textContent = "正在检索通知、阅读相关正文和附件并整理结果，请稍候…";
  stopButton.disabled = false;
  byId("results-title").textContent = school.cn + " · 检索中";
  byId("results-meta").textContent = "";
  submitButton.disabled = true;
  submitButton.firstChild.textContent = "检索中 ";
  const request = new AbortController();
  researchRequest = request;
  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: request.signal,
      body: JSON.stringify({
        school_name: school.cn,
        website: website.value.trim(),
        keywords: byId("keywords").value.trim()
      })
    });
    const data = await response.json().catch(() => null);
    if (researchRequest !== request) return;
    if (!response.ok) {
      const detail = data?.detail;
      throw new Error(detail?.message || (response.status === 404
        ? "检索 API 未连接，请启动 FastAPI 服务。"
        : "检索失败，请稍后重试。"));
    }
    renderResults(data);
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (researchRequest !== request || error.name === "AbortError") return;
    byId("results-title").textContent = school.cn + " · 检索未完成";
    byId("result-error").textContent = error instanceof Error ? error.message : "检索失败，请稍后重试。";
    byId("result-error").hidden = false;
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } finally {
    if (researchRequest === request) {
      researchRequest = null;
      byId("run-state").hidden = true;
      stopButton.disabled = true;
      submitButton.disabled = false;
      submitButton.firstChild.textContent = "开始检索 ";
    }
  }
});

selectSchool(schools[0]);
