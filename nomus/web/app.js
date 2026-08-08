"use strict";

const $ = (sel) => document.querySelector(sel);
const chat = $("#chat");

let lastArticles = [];

/* ---------- утилиты ---------- */

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function append(node) {
  const ph = chat.querySelector(".placeholder");
  if (ph) ph.remove();
  chat.appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------- ссылки на бота ---------- */

async function loadBotLink() {
  try {
    const r = await fetch("/api/health");
    const { bot_url } = await r.json();
    ["#tg-header", "#tg-hero", "#tg-cta", "#tg-footer"].forEach((id) => {
      const a = $(id);
      if (a) a.href = bot_url;
    });
  } catch (e) {
    console.warn("не удалось получить ссылку на бота", e);
  }
}

/* ---------- контакты ---------- */

async function loadContacts() {
  const box = $("#contact-list");
  try {
    const r = await fetch("/api/contacts");
    const { contacts } = await r.json();
    box.innerHTML = contacts
      .map((c) => {
        const urgent = c.value.includes("116 16");
        return `<div class="contact ${urgent ? "urgent" : ""}">
          <div class="name">${esc(c.name)}</div>
          <div class="num">${esc(c.value)}</div>
          <div class="purpose">${esc(c.purpose)}</div>
        </div>`;
      })
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="contact urgent">
      <div class="name">Горячая линия по борьбе с торговлей людьми</div>
      <div class="num">116 16</div>
      <div class="purpose">Круглосуточно, бесплатно, анонимно</div></div>`;
  }
}

/* ---------- рендер ответа ---------- */

function renderRedFlag(triggers) {
  const t = triggers && triggers.length ? triggers.map(esc).join(", ") : "признаки принудительного труда";
  return el(`<div class="msg alert-red">
    <h4>🚨 Важно: в вашей ситуации есть ${t}</h4>
    <p>Позвоните на горячую линию <b>116 16</b> — национальная линия по борьбе
       с торговлей людьми. Круглосуточно, бесплатно, анонимно.</p>
    <p>Также можно обратиться в НПО «Sana Sezim» или консульство вашей страны.</p>
  </div>`);
}

function renderSources(sources) {
  if (!sources || !sources.length) return "";
  const items = sources
    .map((s) => {
      const label = `${esc(s.doc_short)} ст. ${esc(s.article_num)}`;
      const title = esc(s.article_title || "");
      const inner = `${label} <b>${s.score}</b>`;
      return s.url
        ? `<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener" title="${title}">${inner}</a>`
        : `<span class="src" title="${title}">${inner}</span>`;
    })
    .join("");
  return `<div class="meta">Найденные нормы (и оценка релевантности):</div>
          <div class="sources">${items}</div>`;
}

function renderAnswer(d) {
  const parts = [];

  parts.push(`<h4>📌 Суть ситуации</h4><p>${esc(d.summary)}</p>`);

  if (d.rights && d.rights.length) {
    const items = d.rights
      .map(
        (r) =>
          `<li>${esc(r.statement)}<br>
           <span class="cite">— ст. ${esc(r.article)} ${esc(r.doc_short)}</span></li>`
      )
      .join("");
    parts.push(`<h4>⚖️ Ваши права</h4><ul>${items}</ul>`);
  }

  if (d.action_plan && d.action_plan.length) {
    const steps = d.action_plan
      .slice()
      .sort((a, b) => a.step - b.step)
      .map((s) => `<li>${esc(s.action)}${s.why ? `<br><span class="cite">${esc(s.why)}</span>` : ""}</li>`)
      .join("");
    parts.push(`<h4>🧭 План действий</h4><ol>${steps}</ol>`);
  }

  if (d.contacts && d.contacts.length) {
    parts.push(`<h4>📞 Куда обратиться</h4><ul>${d.contacts.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`);
  }

  parts.push(renderSources(d.sources));
  parts.push(`<div class="meta">Ответ за ${(d.latency_ms / 1000).toFixed(1)} с.
    Это правовая информация, а не юридическая консультация.</div>`);

  return el(`<div class="msg">${parts.join("")}</div>`);
}

function renderWarning(text) {
  return el(`<div class="msg alert-warn">
    <h4>⚠️ Предупреждение</h4><p>${esc(text)}</p></div>`);
}

function renderAbstain(d) {
  return el(`<div class="msg alert-info">
    <h4>🤷 ${esc(d.abstain_reason || "Я не нашёл точной нормы")}</h4>
    <p>Я отвечаю только тогда, когда могу подтвердить ответ конкретной статьёй закона.
       Отвечать наугад в правовых вопросах опасно.</p>
    <p>Обратитесь за живой помощью: <b>1414</b> — единый контакт-центр,
       или к юристам НПО (см. раздел «Живая помощь» ниже).</p>
  </div>`);
}

function renderError() {
  return el(`<div class="msg alert-warn">
    <h4>😔 Сервис временно недоступен</h4>
    <p>Попробуйте ещё раз через пару минут. Если вопрос срочный:
       <b>1414</b> — единый контакт-центр, <b>116 16</b> — горячая линия
       по борьбе с торговлей людьми.</p></div>`);
}

/* ---------- форма заявления ---------- */

const CLAIM_FIELDS = [
  ["full_name", "ФИО полностью"],
  ["citizenship", "Гражданство"],
  ["employer", "Работодатель (компания или ИП)"],
  ["work_period", "Период работы"],
  ["debt_amount", "Сумма долга, тенге"],
  ["contact", "Ваш контакт (телефон)"],
];

function renderClaimOffer() {
  const inputs = CLAIM_FIELDS.map(
    ([name, label]) =>
      `<div class="field"><label for="cf-${name}">${label}</label>
       <input type="text" id="cf-${name}" maxlength="300"></div>`
  ).join("");

  const node = el(`<div class="msg alert-info">
    <h4>📄 Сформировать заявление в госинспекцию труда</h4>
    <p>Заполню шаблон заявления о невыплате зарплаты и добавлю статьи из ответа выше.
       Данные никуда не сохраняются — только в ваш файл.</p>
    <div class="claim-grid">${inputs}</div>
    <button class="btn btn-primary" id="claim-btn">Скачать .docx</button>
    <div class="meta" id="claim-status"></div>
  </div>`);

  node.querySelector("#claim-btn").addEventListener("click", () => downloadClaim(node));
  return node;
}

async function downloadClaim(node) {
  const btn = node.querySelector("#claim-btn");
  const status = node.querySelector("#claim-status");
  const payload = { violated_articles: lastArticles };
  for (const [name] of CLAIM_FIELDS) {
    payload[name] = node.querySelector(`#cf-${name}`).value.trim();
  }
  if (!payload.full_name || !payload.employer) {
    status.textContent = "Заполните хотя бы ФИО и работодателя.";
    return;
  }

  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> Формирую документ…';
  try {
    const r = await fetch("/api/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "zayavlenie_gosinspekcia_truda.docx";
    a.click();
    URL.revokeObjectURL(url);
    status.textContent = "Готово. Проверьте данные, распечатайте и подпишите.";
  } catch (e) {
    status.textContent = "Не удалось сформировать документ. Попробуйте в Telegram-боте.";
  } finally {
    btn.disabled = false;
  }
}

/* ---------- основной запрос ---------- */

async function ask() {
  const question = $("#question").value.trim();
  if (question.length < 3) {
    $("#question").focus();
    return;
  }

  const citSelect = $("#citizenship");
  const payload = {
    question,
    citizenship: citSelect.value,
    risk: $("#risk").value,
  };

  append(el(`<div class="msg user"><h4>🙋 Ваш вопрос</h4><p>${esc(question)}</p>
    <div class="meta">${esc(citSelect.options[citSelect.selectedIndex].text)} ·
    ${esc($("#risk").options[$("#risk").selectedIndex].text)}</div></div>`));

  const btn = $("#ask-btn");
  btn.disabled = true;
  const loading = el(`<div class="msg"><h4><span class="spinner"></span> Ищу норму в законах РК…</h4>
    <div class="meta">Поиск по 1817 статьям, проверка цитат</div></div>`);
  append(loading);

  try {
    const r = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    loading.remove();

    if (r.status === 429) {
      append(el(`<div class="msg alert-warn"><h4>⏳ Слишком много запросов</h4>
        <p>Продолжите в Telegram-боте — там лимиты выше.</p></div>`));
      return;
    }
    if (!r.ok) throw new Error("HTTP " + r.status);

    const d = await r.json();

    if (d.red_flag) append(renderRedFlag(d.red_flag_triggers));

    if (d.kind === "answer") {
      append(renderAnswer(d));
      if (d.risk_warning) append(renderWarning(d.risk_warning));
      lastArticles = (d.rights || []).map((x) => `ст. ${x.article} ${x.doc_short} (${x.statement})`);
      if (d.offer_document === "labor_inspection_claim") append(renderClaimOffer());
    } else if (d.kind === "abstain") {
      append(renderAbstain(d));
    } else {
      append(renderError());
    }
  } catch (e) {
    loading.remove();
    append(renderError());
  } finally {
    btn.disabled = false;
  }
}

/* ---------- инициализация ---------- */

$("#ask-btn").addEventListener("click", ask);

$("#question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask();
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    $("#question").value = chip.dataset.q;
    $("#question").focus();
  });
});

loadBotLink();
loadContacts();
