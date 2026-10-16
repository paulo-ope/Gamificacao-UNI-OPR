import type { SupportFeedback, SupportFeedbackIndicator, SupportMacroCardStatus } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";
import { FOLLOW_UP, STATUS_LABEL, dateBr, periodTargetLabel, weeklyTargetLabel } from "./feedback-format";

// PDF do Feedback no papel timbrado da Uni: mesma paleta e desenho do e-mail do workspace (faixa degradê, logo,
// cartões, azul/verde-água). Abre uma janela só com o documento e chama a impressão (Salvar como PDF).
// `@page { margin: 0 }` tira o cabeçalho e o rodapé do navegador (data, "about:blank"); a margem fica no corpo.

const PILL: Record<SupportMacroCardStatus, { bg: string; fg: string }> = {
  ok: { bg: "#dcfce7", fg: "#166534" },
  attention: { bg: "#fef3c7", fg: "#92400e" },
  critical: { bg: "#fee2e2", fg: "#991b1b" },
  partial: { bg: "#e2e8f0", fg: "#475569" },
  no_data: { bg: "#e2e8f0", fg: "#475569" },
  no_target: { bg: "#e2e8f0", fg: "#475569" },
};

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function pill(status: SupportMacroCardStatus) {
  const color = PILL[status];
  return `<span class="pill" style="background:${color.bg};color:${color.fg}">${STATUS_LABEL[status]}</span>`;
}

const STYLE = `
@page { size: A4; margin: 0 }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact }
body { margin: 0; font-family: 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #152747; background: #fff }
.bar { height: 6px; background: linear-gradient(90deg, #2d5fff, #27d9bf) }
.page { padding: 10mm 14mm 8mm }
.head { display: flex; align-items: center; justify-content: space-between }
.head img { height: 46px }
.badge { border: 1px solid #d3e0ff; background: #edf2ff; color: #2d5fff; border-radius: 999px; padding: 4px 12px; font-size: 10px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase }
.kicker { margin: 14px 0 2px; font-size: 10px; font-weight: 700; letter-spacing: 1.6px; text-transform: uppercase; color: #2d5fff }
h1 { margin: 0; font-size: 24px; line-height: 1.2 }
.sub { margin: 2px 0 0; font-size: 12px; color: #5f7391 }
.summary { display: flex; gap: 8px; margin: 12px 0 4px }
.chip { flex: 1; border: 1px solid #d3e0ff; background: #edf2ff; border-radius: 10px; padding: 7px 10px }
.chip small { display: block; font-size: 9px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #5f7391 }
.chip strong { font-size: 17px }
h2 { margin: 14px 0 6px; font-size: 10px; font-weight: 700; letter-spacing: 1.6px; text-transform: uppercase; color: #2d5fff }
table { width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid #dfe7f2; border-radius: 10px; overflow: hidden }
th { background: #edf2ff; color: #5f7391; font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase; text-align: left; padding: 6px 10px }
td { padding: 6px 10px; font-size: 12px; border-top: 1px solid #dfe7f2 }
td.num { font-weight: 700; font-variant-numeric: tabular-nums }
.pill { display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 10px; font-weight: 700 }
.goals { display: grid; grid-template-columns: 1fr 1fr; gap: 6px }
.goal { border: 1px solid #dfe7f2; border-radius: 8px; padding: 6px 10px; display: flex; justify-content: space-between; gap: 8px; font-size: 11px }
.goal b { white-space: nowrap }
.tips { margin: 0; padding: 0; list-style: none }
.tips li { background: #f7f9fc; border-left: 3px solid #27d9bf; border-radius: 4px; padding: 6px 10px; margin-bottom: 5px; font-size: 11px; line-height: 1.45 }
.tips li span { color: #5f7391; font-weight: 700; font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase; margin-right: 8px }
.plan { min-height: 26mm; border: 1px solid #d3e0ff; background: #edf2ff; border-radius: 10px; padding: 8px 12px; font-size: 12px; line-height: 1.6; white-space: pre-wrap }
.lines { min-height: 26mm; border: 1px solid #d3e0ff; background: #edf2ff; border-radius: 10px; padding: 0 12px;
  background-image: repeating-linear-gradient(transparent, transparent 25px, #b9cdf5 25px, #b9cdf5 26px) }
.foot { margin-top: 10mm; text-align: center; font-size: 10px; color: #5f7391; line-height: 1.6 }
.foot span { color: #97accf }
`;

export function printFeedback(data: SupportFeedback, pending: SupportFeedbackIndicator[], plan: string) {
  const rows = data.indicators
    .map(
      (item) =>
        `<tr><td><b>${escapeHtml(item.label)}</b></td><td class="num">${escapeHtml(formatCardValue(item, item.value))}</td><td>${escapeHtml(periodTargetLabel(item))}</td><td>${pill(item.status)}</td></tr>`,
    )
    .join("");
  const goals = pending.length
    ? `<div class="goals">${pending.map((item) => `<div class="goal"><span>${escapeHtml(item.label)}</span><b>${escapeHtml(weeklyTargetLabel(item))}</b></div>`).join("")}</div>`
    : `<div class="goal">Manter o desempenho atual na próxima semana.</div>`;
  const tips = pending.length
    ? `<ol class="tips">${pending.map((item, index) => `<li><span>Prioridade ${index + 1}</span>${escapeHtml(FOLLOW_UP[item.key] ?? item.label)}</li>`).join("")}</ol>`
    : "";
  const note = plan.trim();
  const logo = `${window.location.origin}/brand/uni-logo.png`;
  const generated = new Date().toLocaleString("pt-BR", { timeZone: "America/Porto_Velho" });

  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feedback - ${escapeHtml(data.name)}</title><style>${STYLE}</style></head><body>
<div class="bar"></div><div class="page">
<div class="head"><img src="${logo}" alt="Uni Internet"><span class="badge">Suporte Interno</span></div>
<p class="kicker">Feedback individual</p>
<h1>${escapeHtml(data.name)}</h1>
<p class="sub">Período: ${dateBr(data.date_from)} a ${dateBr(data.date_to)}</p>
<div class="summary">
<div class="chip"><small>Status geral</small>${pill(data.summary.overall)}</div>
<div class="chip"><small>Dentro da meta</small><strong>${data.summary.ok}</strong></div>
<div class="chip"><small>Atenção</small><strong>${data.summary.attention}</strong></div>
<div class="chip"><small>Evoluir</small><strong>${data.summary.critical}</strong></div>
</div>
<h2>Indicadores do colaborador</h2>
<table><thead><tr><th>Indicador</th><th>Resultado</th><th>Meta</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>
<h2>Meta para a próxima semana</h2>${goals}
${tips ? `<h2>Como acompanhar</h2>${tips}` : ""}
<h2>Combinado da conversa</h2>
${note ? `<div class="plan">${escapeHtml(note)}</div>` : `<div class="lines"></div>`}
<div class="foot">UNI Internet &middot; Ecossistema operacional<br><span>Documento gerado pelo UNI Workspace em ${escapeHtml(generated)}</span></div>
</div>
<script>window.addEventListener("load", function () { setTimeout(function () { window.print(); }, 200); });</script>
</body></html>`;

  const popup = window.open("", "_blank", "width=900,height=1000");
  if (!popup) return;
  popup.document.write(html);
  popup.document.close();
}
