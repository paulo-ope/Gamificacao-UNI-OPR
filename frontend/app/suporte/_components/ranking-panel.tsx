"use client";

import { AlertCircle, CalendarDays, Crown, Headphones, Info, Loader2, RefreshCw, Trophy, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { SupportRanking, SupportRankingCriterion, SupportRankingRow } from "@/lib/types";

import styles from "./opa-ranking.module.css";

function numeric(value: number | null | undefined, digits = 0) {
  return value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function monthLabel(date: string) {
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));
}

function initials(name: string) {
  return name.trim().split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toLocaleUpperCase("pt-BR") || "?";
}

function criterionValue(criterion: SupportRankingCriterion | null | undefined, unit: "score" | "seconds" | "count") {
  const value = criterion?.value;
  if (value == null || !Number.isFinite(value)) return "—";
  if (unit !== "seconds") return numeric(value, unit === "score" ? 2 : 0);
  const seconds = Math.max(0, Math.round(value));
  return [Math.floor(seconds / 3600), Math.floor(seconds % 3600 / 60), seconds % 60].map((part) => String(part).padStart(2, "0")).join(":");
}

function Points({ value, active }: { value: number | null | undefined; active: boolean }) {
  if (!active || value == null || !Number.isFinite(value)) return <span className={styles.unavailable}>—</span>;
  return <span className={`${styles.change} ${value > 0 ? styles.positive : value < 0 ? styles.negative : styles.neutral}`} aria-label={`${value > 0 ? "+" : ""}${numeric(value)} pontos`}>{value > 0 ? "+" : ""}{numeric(value)}</span>;
}

function CriterionCell({ criterion, unit, active }: { criterion: SupportRankingCriterion | null | undefined; unit: "score" | "seconds" | "count"; active: boolean }) {
  return <TableCell className={styles.criterionCell}>
    <span className={styles.metric}>{criterionValue(criterion, unit)}</span>
    <div className={styles.criterionBadges}><Points value={criterion?.points} active={active} />{criterion?.partial ? <span className={styles.partial} title="TMR calculado para menos da metade dos atendimentos com humano: a pontuação usa uma amostra pequena.">Amostra parcial</span> : null}</div>
    {criterion?.detail && active ? <span className={styles.metricHint}>{criterion.detail}</span> : null}
  </TableCell>;
}

function PodiumCard({ row }: { row: SupportRankingRow }) {
  const position = row.position!;
  const champion = position === 1;
  return (
    <li className={`${styles.podiumCard} ${styles[`place${position}`]}`}>
      <div className={styles.cardTop}><span className={styles.placeLabel}>{position}º lugar</span>{champion ? <span className={styles.leaderBadge}><Crown size={13} aria-hidden="true" />Líder do mês</span> : <span className={styles.cardSubtitle}>{position === 2 ? "Vice-líder" : "Terceiro colocado"}</span>}</div>
      <div className={styles.trophyWrap}><Trophy aria-hidden="true" strokeWidth={1.5} /><span className={styles.trophyRank}>{position}</span></div>
      <h4 className={styles.collaboratorName} title={row.name}>{row.name?.trim() || "Nome não informado"}</h4>
      <p className={styles.cardScore}>{numeric(row.total_points)}<span>pontos</span></p>
      <div className={styles.cardFooter}><Headphones size={14} aria-hidden="true" /><span>{numeric(row.attendances)} atendimentos no mês</span></div>
    </li>
  );
}

type RankingViewProps = {
  data: SupportRanking | null;
  month?: string;
  loading: boolean;
  error: string | null;
  onMonthChange: (month: string) => void;
  onRefresh: () => void;
};

// All points, positions and ties come directly from the monthly ranking API.
export function RankingView({ data, month, loading, error, onMonthChange, onRefresh }: RankingViewProps) {
  const ranked = data?.rows.filter((row) => row.active) ?? [];
  const idle = data?.rows.filter((row) => !row.active) ?? [];
  const podium = ranked.filter((row) => row.position != null && row.position >= 1 && row.position <= 3);
  const selectedMonth = month ?? data?.date_from ?? "";
  const months = data?.months ?? [];
  const showResults = Boolean(data) && !loading && !error;

  return (
    <section className={styles.ranking} aria-labelledby="support-ranking-title" aria-busy={loading}>
      <div className={styles.toolbar}>
        <div className={styles.monthField}><CalendarDays size={17} aria-hidden="true" /><label htmlFor="support-ranking-month">Mês de referência</label><Select id="support-ranking-month" value={selectedMonth} disabled={!data || loading} onChange={(event) => onMonthChange(event.target.value)}>
          {!selectedMonth ? <option value="">Carregando meses…</option> : null}
          {selectedMonth && !months.some((item) => item.date_from === selectedMonth) ? <option value={selectedMonth}>{monthLabel(selectedMonth)}</option> : null}
          {months.map((item) => <option key={item.date_from} value={item.date_from}>{monthLabel(item.date_from)}</option>)}
        </Select></div>
        <Button variant="outline" size="sm" disabled={loading} onClick={onRefresh}><RefreshCw size={14} aria-hidden="true" />Atualizar ranking</Button>
      </div>
      <p className={styles.periodNote}>Pontuação do mês inteiro, pelo Quadro de Pontuação do Suporte Interno. O mês em andamento soma até hoje.</p>
      <div className={styles.sectionHeading}>
        <div><p className={styles.eyebrow}>Reconhecimento da equipe</p><h3 id="support-ranking-title">Destaques do suporte{selectedMonth ? <span>{monthLabel(selectedMonth)}</span> : null}</h3><p className={styles.description}>Cada atendimento faz a diferença. Conheça quem se destaca no mês.</p></div>
        <span className={styles.sourceBadge}><span />Dados do OPA Suite</span>
      </div>
      <div role="status" aria-live="polite">
        {loading ? <div className={styles.loadingState}><Loader2 className="animate-spin" size={20} aria-hidden="true" /><p>{data ? "Atualizando ranking do mês…" : "Carregando ranking do mês…"}</p></div> : null}
        {showResults && !ranked.length ? <div className={styles.emptyState}><Trophy size={32} aria-hidden="true" /><h4>O próximo destaque pode estar aqui</h4><p>Nenhum atendimento da equipe neste mês.</p><p>Selecione outro mês para consultar a classificação.</p></div> : null}
      </div>
      {error && !loading ? <div className={styles.errorState} role="alert"><AlertCircle size={22} aria-hidden="true" /><div><h4>Não foi possível carregar o ranking</h4><p>{error}</p></div><Button variant="outline" size="sm" onClick={onRefresh}>Tentar novamente</Button></div> : null}
      {showResults && podium.length > 0 ? <>
        <ol className={styles.podium} aria-label="Pódio do ranking mensal por pontuação">{podium.map((row) => <PodiumCard key={row.attendant_id} row={row} />)}</ol>
        {podium.length < 3 ? <p className={styles.availability}>O pódio exibe {podium.length === 1 ? "o único colaborador classificado" : "os dois colaboradores classificados"} neste mês.</p> : null}
      </> : null}
      <div className={styles.tablePanel}>
        <div className={styles.tableHeading}><div><p className={styles.eyebrow}>Pontuação do mês</p><h4>Classificação geral <span className={styles.count}>{showResults ? numeric(ranked.length) : "—"} {ranked.length === 1 ? "colaborador classificado" : "colaboradores classificados"}</span></h4>{data?.tie_break ? <p>{data.tie_break}</p> : null}</div><Users size={20} aria-hidden="true" /></div>
        <Table className={styles.table}>
          <caption className="sr-only">Ranking mensal do suporte{selectedMonth ? ` de ${monthLabel(selectedMonth)}` : ""}. Valores e pontuações calculados pelo Quadro de Pontuação do Suporte Interno.</caption>
          <TableHeader><TableRow><TableHead scope="col">Posição</TableHead><TableHead scope="col">Colaborador</TableHead><TableHead scope="col" className="text-center">Avaliação</TableHead><TableHead scope="col" className="text-center">TMR</TableHead><TableHead scope="col" className="text-center">Ligações</TableHead><TableHead scope="col" className="text-right">Pontuação total</TableHead></TableRow></TableHeader>
          <TableBody>
            {showResults && [...ranked, ...idle].map((row) => <TableRow key={row.attendant_id} className={row.active && row.position != null && row.position <= 3 ? styles.topRow : undefined}>
              <TableCell><span className={`${styles.position} ${row.active && row.position != null && row.position <= 3 ? styles[`medal${row.position}`] : ""}`}>{row.active && row.position != null && row.position <= 3 ? <Trophy size={13} aria-hidden="true" /> : null}{row.position != null ? `${numeric(row.position)}º` : "—"}</span></TableCell>
              <TableCell><div className={styles.person}><span className={styles.avatar} aria-hidden="true">{initials(row.name || "")}</span><div className={styles.personText}><span className={styles.personName} title={row.name}>{row.name?.trim() || "Nome não informado"}</span>{row.active ? <span className={styles.metricHint}>{numeric(row.attendances)} atendimentos</span> : <span className={styles.metricHint}>Sem atendimento no mês</span>}</div></div></TableCell>
              <CriterionCell criterion={row.rating} unit="score" active={row.active} /><CriterionCell criterion={row.tmr} unit="seconds" active={row.active} /><CriterionCell criterion={row.calls} unit="count" active={row.active} />
              <TableCell className={styles.totalPoints}>{row.active ? numeric(row.total_points) : "—"}</TableCell>
            </TableRow>)}
            {!showResults || !data?.rows.length ? <TableRow><TableCell colSpan={6} className="py-12 text-center text-slate-500">{loading ? "Aguarde a atualização dos dados." : error ? "Ranking indisponível. Tente carregar novamente." : "Sem resultados para exibir."}</TableCell></TableRow> : null}
          </TableBody>
        </Table>
        <div className={styles.tableFooter}><span><Headphones size={14} aria-hidden="true" />Atendimentos do Suporte Interno</span><span>“—” indica dado indisponível ou colaborador sem classificação.</span></div>
      </div>
      {showResults && data ? <details className={styles.rulesPanel}><summary><Info size={16} aria-hidden="true" />Entenda o Quadro de Pontuação<span>Regras e critérios</span></summary><div className={styles.rulesGrid}>{data.rules.map((rule) => <div key={rule.key}><h4>{rule.label}</h4><ul>{rule.lines.map((line) => <li key={line}>{line}</li>)}</ul></div>)}</div>{data.not_included ? <p className={styles.exclusions}>{data.not_included}</p> : null}</details> : null}
    </section>
  );
}

export function RankingPanel() {
  const [month, setMonth] = useState<string>();
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<SupportRanking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.supportRanking(month).then((result) => {
      if (!cancelled) setData(result);
    }).catch(() => {
      if (!cancelled) setError("Verifique sua conexão e tente novamente. Se o problema continuar, contate o administrador.");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [month, revision]);

  return <RankingView data={data} month={month} loading={loading} error={error} onMonthChange={(next) => { setLoading(true); setMonth(next); }} onRefresh={() => { setLoading(true); setRevision((current) => current + 1); }} />;
}
