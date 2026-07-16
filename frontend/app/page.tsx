"use client";

import { CheckCircle2, FileText, LoaderCircle, ShieldCheck, UploadCloud } from "lucide-react";
import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const ANALYZE_API_URL = "http://localhost:8000/analyze";
const STATUS_API_URL = "http://localhost:8000/status";
const UPLOAD_API_URL = "http://localhost:8000/upload";
const DRAFT_API_URL = "http://localhost:8000/draft";
const REPORT_DOWNLOAD_URL = "http://localhost:8000/report";
const DISCLAIMER = "LedgerGuard provides informational analysis, not legal or financial advice.";

type Evidence = { record_type?: string; record_id: string; page_ref: string; excerpt: string };
type ImpactProvenance = { rules_engine_discrepancy_id?: string; rules_engine_dollar_impact?: string };
type ReportItem = { candidate_id: string; discrepancy_type: string; dollar_impact: string; confidence_score: number | null; evidence: Evidence[]; impact_provenance?: ImpactProvenance | null };
type ReportPayload = {
  disclaimer?: string;
  report_id?: string;
  summary: { confirmed_discrepancy_count: number; total_confirmed_dollar_impact: string };
  confirmed_discrepancies: ReportItem[];
  dismissed_items: ReportItem[];
};
type DropZoneProps = { label: string; description: string; file: File | null; onFileSelected: (file: File | null) => void };
type SupportingDocument = { file: File; documentType: "invoice" | "contract" | "statement" };
type SupportingDropZoneProps = {
  documents: SupportingDocument[];
  onDocumentsSelected: (documents: SupportingDocument[]) => void;
  onDocumentRemoved: (index: number) => void;
  onDocumentTypeChanged: (index: number, documentType: SupportingDocument["documentType"]) => void;
};
type DisputeDraft = { id: string; discrepancy_id: string; subject: string; body: string; status: "draft" };
type AnalysisStatus = { job_id: string; stage: string; completed_stages?: string[] } & Partial<ReportPayload>;

const PROCESSING_STAGES = [
  { id: "ingesting", label: "Ingesting" },
  { id: "normalizing", label: "Normalizing" },
  { id: "rules_engine", label: "Rules engine" },
  { id: "triage", label: "Triage" },
  { id: "investigating", label: "Investigating" },
  { id: "synthesizing", label: "Synthesizing" },
  { id: "complete", label: "Complete" },
] as const;

function isPdf(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function money(value: string) {
  const amount = Number(value);
  return Number.isFinite(amount) ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount) : value;
}

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function citedAmount(item: ReportItem, label: string) {
  const excerpt = item.evidence.find((citation) => citation.excerpt.toLowerCase().includes(label.toLowerCase()))?.excerpt;
    return excerpt?.match(new RegExp(`${label}\\s*:\\s*(-?\\d+(?:\\.\\d{1,2})?)`, "i"))?.[1] ?? null;
}

function explanationFor(item: ReportItem, outcome: "confirmed" | "dismissed") {
  const confirmed = outcome === "confirmed";
  if (item.discrepancy_type === "rate_violation") {
    const billed = citedAmount(item, "Billed unit price");
    const contracted = citedAmount(item, "Agreed unit price");
    if (billed && contracted) {
      return confirmed
        ? `This was flagged because the invoice billed ${money(billed)} per unit against the contracted ${money(contracted)} rate, creating a stored ${money(item.dollar_impact)} difference.`
        : `This was cleared after reviewing the billed ${money(billed)} rate against the contracted ${money(contracted)} rate; the investigation did not confirm a rate violation.`;
    }
  }
  if (item.discrepancy_type === "duplicate") {
    const firstCitation = item.evidence[0]?.excerpt ?? "the cited charge";
    const description = firstCitation.split(";")[0];
    const amount = citedAmount(item, "total");
    const charge = amount ? `${money(amount)} ${description} charge` : description;
    if (confirmed) {
      return `This was flagged because the same ${charge} appears ${item.evidence.length} times in the cited records, with ${money(item.dollar_impact)} stored as the duplicate impact.`;
    }
    return `This was cleared after reviewing ${item.evidence.length} cited record${item.evidence.length === 1 ? "" : "s"} for a possible ${charge}; the investigation did not confirm duplicate billing.`;
  }
  if (item.discrepancy_type === "price_hike") {
    const oldPrice = citedAmount(item, "Earlier recorded unit price");
    const newPrice = citedAmount(item, "Later recorded unit price");
    if (oldPrice && newPrice) {
      return confirmed
        ? `This was flagged because the rate changed from ${money(oldPrice)} to ${money(newPrice)} and the investigation confirmed the change was unauthorized.`
        : `This was cleared because the rate changed from ${money(oldPrice)} to ${money(newPrice)}, and the investigation confirmed that change was authorized.`;
    }
  }
  return confirmed
    ? "This was flagged because the reviewed records support a confirmed discrepancy."
    : "This was cleared because the investigation reviewed these records and did not confirm a discrepancy.";
}

function DropZone({ label, description, file, onFileSelected }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  function select(fileList: FileList | null) {
    const selected = fileList?.item(0) ?? null;
    if (selected && isPdf(selected)) onFileSelected(selected);
  }
  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    select(event.dataTransfer.files);
  }
  function handleChange(event: ChangeEvent<HTMLInputElement>) { select(event.target.files); }

  return (
    <div
      className={cn(
        "rounded-2xl border border-dashed p-6 text-center transition-all",
        isDragging ? "border-indigo-500 bg-indigo-50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm",
      )}
      onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <input ref={inputRef} className="sr-only" type="file" accept="application/pdf" onChange={handleChange} />
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><UploadCloud className="h-5 w-5" aria-hidden="true" /></div>
      <h2 className="mt-3 text-sm font-semibold text-slate-950">{label}</h2>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
      {file ? (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm text-slate-700">
          <FileText className="h-4 w-4 text-indigo-600" aria-hidden="true" />
          <span className="font-medium">{file.name}</span>
          <button className="text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-slate-900" type="button" onClick={() => onFileSelected(null)}>Remove</button>
        </div>
      ) : (
        <Button className="mt-4 rounded-lg border-slate-200" variant="outline" type="button" onClick={() => inputRef.current?.click()}>Choose PDF</Button>
      )}
    </div>
  );
}

function SupportingDropZone({ documents, onDocumentsSelected, onDocumentRemoved, onDocumentTypeChanged }: SupportingDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function addFiles(fileList: FileList | null) {
    const incoming = Array.from(fileList ?? []).filter(isPdf);
    if (!incoming.length) return;
    onDocumentsSelected([...documents, ...incoming.map((file) => ({ file, documentType: "contract" as const }))]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    addFiles(event.dataTransfer.files);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  return (
    <div
      className={cn(
        "rounded-2xl border border-dashed p-6 text-center transition-all",
        isDragging ? "border-indigo-500 bg-indigo-50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm",
      )}
      onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <input ref={inputRef} className="sr-only" type="file" accept="application/pdf" multiple onChange={handleChange} />
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><UploadCloud className="h-5 w-5" aria-hidden="true" /></div>
      <h2 className="mt-3 text-sm font-semibold text-slate-950">Supporting documents</h2>
      <p className="mt-1 text-sm text-slate-500">Optional. Add contracts, amendments, or other supporting PDFs.</p>
      <Button className="mt-4 rounded-lg border-slate-200" variant="outline" type="button" onClick={() => inputRef.current?.click()}>{documents.length ? "Add another PDF" : "Choose PDFs"}</Button>
      {documents.length ? (
        <ul className="mx-auto mt-5 max-w-xl space-y-2 text-left">
          {documents.map((document, index) => (
            <li key={`${document.file.name}-${document.file.lastModified}-${index}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700 sm:flex-nowrap">
              <span className="flex min-w-0 items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-indigo-600" aria-hidden="true" /><span className="truncate font-medium">{document.file.name}</span></span>
              <span className="flex shrink-0 items-center gap-3">
                <label className="sr-only" htmlFor={`supporting-document-type-${index}`}>Document type for {document.file.name}</label>
                <select id={`supporting-document-type-${index}`} value={document.documentType} onChange={(event) => onDocumentTypeChanged(index, event.target.value as SupportingDocument["documentType"])} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-600">
                    <option value="contract">Contract</option>
                    <option value="statement">Statement</option>
                    <option value="invoice">Invoice</option>
                </select>
                <button className="text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-slate-900" type="button" onClick={() => onDocumentRemoved(index)}>Remove</button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return (
    <ul className="space-y-3 border-l-2 border-indigo-100 pl-4 text-sm text-slate-600">
      {evidence.map((item) => (
        <li key={`${item.record_id}-${item.page_ref}`}>
          <p className="leading-6 text-slate-700">{item.excerpt}</p>
          <p className="mt-1 text-xs font-medium text-slate-500">Record {item.record_id} · Page {item.page_ref}</p>
        </li>
      ))}
    </ul>
  );
}

function ReasoningContent({ item, outcome }: { item: ReportItem; outcome: "confirmed" | "dismissed" }) {
  const confidence = item.confidence_score === null ? "Not available" : `${Math.round(item.confidence_score * 100)}%`;
  const impact = item.impact_provenance?.rules_engine_dollar_impact;
  const calculationId = item.impact_provenance?.rules_engine_discrepancy_id;
  const introduction = explanationFor(item, outcome);

  return (
    <div className="space-y-4 rounded-xl bg-slate-50 p-4 text-sm">
      <p className="leading-6 text-slate-700">{introduction}</p>
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Evidence reviewed</p>
        <EvidenceList evidence={item.evidence} />
      </div>
      <div className="grid gap-3 border-t border-slate-200 pt-4 sm:grid-cols-2">
        <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Confidence</p><p className="mt-1 font-semibold text-slate-800">{confidence}</p></div>
        <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Impact source</p><p className="mt-1 font-semibold text-slate-800">{impact ? `${money(impact)} from the rules engine` : "No stored rules-engine impact"}</p></div>
      </div>
      {calculationId ? <p className="text-xs leading-5 text-slate-500">Stored calculation reference: {calculationId}. The displayed impact is not recalculated in this view.</p> : null}
      {outcome === "dismissed" ? <p className="text-xs leading-5 text-slate-500">Cleared items remain visible for review but do not contribute to total confirmed impact.</p> : null}
    </div>
  );
}

function DraftEditor({ draft }: { draft: DisputeDraft }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [copied, setCopied] = useState(false);

  async function copyDraft() {
    await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
    setCopied(true);
  }

  return (
    <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-slate-900">Dispute email draft</p><span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-indigo-700">Manual send only</span></div>
      <label className="mt-4 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor={`draft-subject-${draft.id}`}>Subject</label>
      <input id={`draft-subject-${draft.id}`} value={subject} onChange={(event) => setSubject(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-indigo-500 focus:ring-2" />
      <label className="mt-4 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500" htmlFor={`draft-body-${draft.id}`}>Body</label>
      <textarea id={`draft-body-${draft.id}`} value={body} onChange={(event) => setBody(event.target.value)} rows={11} className="mt-1 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 font-sans text-sm leading-6 text-slate-800 outline-none ring-indigo-500 focus:ring-2" />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs leading-5 text-slate-600">Sending is manual and happens outside LedgerGuard. This app cannot send email.</p><Button className="rounded-lg" type="button" onClick={copyDraft}>{copied ? "Copied" : "Copy to clipboard"}</Button></div>
    </div>
  );
}

function DiscrepancyCard({ item, draft, draftError, isDrafting, onDraft }: { item: ReportItem; draft?: DisputeDraft; draftError?: string; isDrafting: boolean; onDraft: () => void }) {
  return (
    <Card className="overflow-hidden border-slate-200 shadow-[0_8px_30px_rgb(15,23,42,0.05)]">
      <CardHeader className="gap-3 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-600">Confirmed finding</p>
            <CardTitle className="mt-2 text-xl text-slate-950">{titleCase(item.discrepancy_type)}</CardTitle>
          </div>
          <div className="shrink-0 text-right"><p className="text-2xl font-semibold tracking-tight text-slate-950">{money(item.dollar_impact)}</p><p className="mt-1 text-xs font-medium text-slate-500">potential impact</p></div>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-600"><CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" /><span>Confidence: <strong className="font-semibold text-slate-800">{item.confidence_score === null ? "Not available" : `${Math.round(item.confidence_score * 100)}%`}</strong></span></div>
      </CardHeader>
      <CardContent className="border-t border-slate-100 p-5 pt-0 sm:p-6 sm:pt-0">
        <Accordion type="single" collapsible><AccordionItem value="why" className="border-b-0"><AccordionTrigger className="py-4 text-sm font-semibold text-slate-800 hover:no-underline">Why?</AccordionTrigger><AccordionContent className="pb-1"><ReasoningContent item={item} outcome="confirmed" /></AccordionContent></AccordionItem></Accordion>
        <Button className="mt-4 rounded-lg" type="button" onClick={onDraft} disabled={isDrafting}>{isDrafting ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : null}{isDrafting ? "Drafting email..." : "Draft dispute email"}</Button>
        {draftError ? <p className="mt-3 text-sm text-rose-700">{draftError}</p> : null}
        {draft ? <DraftEditor draft={draft} /> : null}
      </CardContent>
    </Card>
  );
}

function Report({ report }: { report: ReportPayload }) {
  const confirmed = useMemo(() => [...report.confirmed_discrepancies].sort((left, right) => Number(right.dollar_impact) - Number(left.dollar_impact)), [report.confirmed_discrepancies]);
  const dismissed = useMemo(() => [...report.dismissed_items].sort((left, right) => Number(right.dollar_impact) - Number(left.dollar_impact)), [report.dismissed_items]);
  const [drafts, setDrafts] = useState<Record<string, DisputeDraft>>({});
  const [draftErrors, setDraftErrors] = useState<Record<string, string>>({});
  const [draftingId, setDraftingId] = useState<string | null>(null);

  async function requestDraft(discrepancyId: string) {
    if (!report.report_id) {
      setDraftErrors((errors) => ({ ...errors, [discrepancyId]: "This report can no longer be used to prepare a draft." }));
      return;
    }
    setDraftingId(discrepancyId);
    setDraftErrors((errors) => ({ ...errors, [discrepancyId]: "" }));
    try {
      const response = await fetch(DRAFT_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_id: report.report_id, discrepancy_id: discrepancyId }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error("draft_request_failed");
      setDrafts((currentDrafts) => ({ ...currentDrafts, [discrepancyId]: payload as DisputeDraft }));
    } catch (error) {
      console.error("LedgerGuard draft request failed:", error);
      setDraftErrors((errors) => ({ ...errors, [discrepancyId]: "The draft could not be prepared. Confirmed evidence is required." }));
    } finally {
      setDraftingId(null);
    }
  }
  return (
    <section className="mt-10 space-y-8" aria-live="polite">
      <Card className="overflow-hidden border-0 bg-slate-950 text-white shadow-[0_20px_55px_rgb(15,23,42,0.24)]">
        <CardHeader className="relative gap-6 p-6 sm:p-8"><div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-indigo-500/20 blur-3xl" aria-hidden="true" />
          <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between"><div><div className="flex items-center gap-2 text-sm font-medium text-indigo-200"><ShieldCheck className="h-4 w-4" aria-hidden="true" />Analysis complete</div><p className="mt-5 text-sm font-medium text-slate-300">Total confirmed impact</p><CardTitle className="mt-1 text-5xl font-semibold tracking-tight text-white">{money(report.summary.total_confirmed_dollar_impact)}</CardTitle></div><div className="flex flex-col items-start gap-4 border-t border-white/15 pt-4 sm:items-end sm:border-l sm:border-t-0 sm:pl-7 sm:pt-0"><div><p className="text-2xl font-semibold text-white">{report.summary.confirmed_discrepancy_count}</p><p className="mt-1 max-w-32 text-sm leading-5 text-slate-300">confirmed {report.summary.confirmed_discrepancy_count === 1 ? "finding" : "findings"} requiring review</p></div>{report.report_id ? <a className="inline-flex h-9 items-center justify-center rounded-lg border border-white/20 bg-white/10 px-3 text-sm font-semibold text-white transition-colors hover:bg-white/20" href={`${REPORT_DOWNLOAD_URL}/${report.report_id}/download`}>Download report</a> : null}</div></div>
        </CardHeader>
      </Card>
      <div><div className="flex items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Review queue</p><h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Confirmed discrepancies</h2></div><p className="hidden text-sm text-slate-500 sm:block">Ranked by dollar impact</p></div><div className="mt-5 space-y-4">{confirmed.length ? confirmed.map((item) => <DiscrepancyCard key={item.candidate_id} item={item} draft={drafts[item.candidate_id]} draftError={draftErrors[item.candidate_id]} isDrafting={draftingId === item.candidate_id} onDraft={() => requestDraft(item.candidate_id)} />) : <p className="text-sm text-slate-600">No confirmed discrepancies were found.</p>}</div></div>
      {dismissed.length ? <Card className="border-slate-200 bg-slate-50/80 text-slate-600 shadow-none"><CardContent className="p-5 pt-0 sm:p-6 sm:pt-0"><Accordion type="single" collapsible><AccordionItem value="dismissed" className="border-b-0"><AccordionTrigger className="text-slate-700 hover:no-underline"><span className="flex items-center gap-2"><span className="rounded-full bg-slate-200 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Not counted</span> Considered items ({dismissed.length})</span></AccordionTrigger><AccordionContent><p className="mb-4 text-sm text-slate-500">These findings were reviewed and do not contribute to the confirmed total.</p><div className="space-y-4">{dismissed.map((item) => <div key={item.candidate_id} className="rounded-xl border border-slate-200 bg-white p-4"><div className="flex justify-between gap-4 text-sm"><span className="font-medium">{titleCase(item.discrepancy_type)}</span><span>{money(item.dollar_impact)}</span></div><Accordion type="single" collapsible><AccordionItem value={`why-${item.candidate_id}`} className="border-b-0"><AccordionTrigger className="py-3 text-sm font-semibold text-slate-700 hover:no-underline">Why?</AccordionTrigger><AccordionContent><ReasoningContent item={item} outcome="dismissed" /></AccordionContent></AccordionItem></Accordion></div>)}</div></AccordionContent></AccordionItem></Accordion></CardContent></Card> : null}
    </section>
  );
}

function ProcessingProgress({ status }: { status: AnalysisStatus }) {
  const completed = new Set(status.completed_stages ?? []);

  return (
    <Card className="mt-8 overflow-hidden border-indigo-100 bg-white shadow-[0_16px_40px_rgb(79,70,229,0.10)]" aria-live="polite">
      <CardHeader className="border-b border-indigo-50 bg-gradient-to-r from-indigo-50 to-white p-6">
        <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white"><LoaderCircle className="h-5 w-5 animate-spin" aria-hidden="true" /></span><div><CardTitle className="text-lg text-slate-950">Analyzing your documents</CardTitle><p className="mt-1 text-sm text-slate-600">Live progress updates appear as each stage finishes.</p></div></div>
      </CardHeader>
      <CardContent className="p-6">
        <ol className="space-y-0">
          {PROCESSING_STAGES.map((stage, index) => {
            const isCompleted = completed.has(stage.id);
            const isActive = status.stage === stage.id || (status.stage === "queued" && index === 0);
            return (
              <li key={stage.id} className="relative flex gap-4 pb-5 last:pb-0">
                {index < PROCESSING_STAGES.length - 1 ? <span className={cn("absolute left-[13px] top-7 h-[calc(100%-8px)] w-px", isCompleted ? "bg-emerald-300" : "bg-slate-200")} aria-hidden="true" /> : null}
                <span className={cn("relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border", isCompleted ? "border-emerald-500 bg-emerald-500 text-white" : isActive ? "border-indigo-600 bg-indigo-600 text-white shadow-[0_0_0_4px_rgb(224,231,255)]" : "border-slate-200 bg-white text-slate-400")}>
                  {isCompleted ? <CheckCircle2 className="h-4 w-4" aria-label={`${stage.label} complete`} /> : isActive ? <LoaderCircle className="h-4 w-4 animate-spin" aria-label={`${stage.label} in progress`} /> : <span className="h-2 w-2 rounded-full bg-current" aria-hidden="true" />}
                </span>
                <div className="pt-0.5"><p className={cn("text-sm font-semibold", isCompleted ? "text-emerald-700" : isActive ? "text-indigo-700" : "text-slate-400")}>{stage.label}</p><p className="mt-0.5 text-xs text-slate-500">{isCompleted ? "Complete" : isActive ? "In progress" : "Waiting"}</p></div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

export default function UploadPage() {
  const [invoice, setInvoice] = useState<File | null>(null);
  const [supportingDocuments, setSupportingDocuments] = useState<SupportingDocument[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus | null>(null);

  function formData() {
    const body = new FormData();
    body.append("file", invoice!);
    body.append("document_type", "invoice");
    supportingDocuments.forEach((supportingDocument) => {
      body.append("supporting_files", supportingDocument.file);
      body.append("supporting_document_types", supportingDocument.documentType);
    });
    return body;
  }

  async function submitFallback() {
    setAnalysisStatus(null);
    try {
      const response = await fetch(UPLOAD_API_URL, { method: "POST", body: formData() });
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error("upload_fallback_failed");
      setReport(payload as ReportPayload);
      setMessage("Live progress was unavailable, so this analysis completed through the standard upload path.");
    } catch (error) {
      console.error("LedgerGuard upload request failed:", error);
      setMessage("The API could not be reached. Make sure it is running on localhost:8000.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function pollStatus(jobId: string): Promise<void> {
    try {
      const response = await fetch(`${STATUS_API_URL}/${jobId}`);
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error("status_request_failed");
      const status = payload as AnalysisStatus;
      setAnalysisStatus(status);
      if (status.stage === "complete") {
        setReport(status as ReportPayload);
        setIsSubmitting(false);
        return;
      }
      if (status.stage === "failed") throw new Error("analysis_failed");
      window.setTimeout(() => { void pollStatus(jobId); }, 1000);
    } catch (error) {
      console.error("LedgerGuard live analysis failed:", error);
      await submitFallback();
    }
  }

  async function submit() {
    if (!invoice || isSubmitting) return;
    setIsSubmitting(true); setMessage(null); setReport(null); setAnalysisStatus({ job_id: "", stage: "queued", completed_stages: [] });
    try {
      const response = await fetch(ANALYZE_API_URL, { method: "POST", body: formData() });
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error("analysis_submit_failed");
      const job = payload as AnalysisStatus;
      setAnalysisStatus(job);
      void pollStatus(job.job_id);
    } catch (error) {
      console.error("LedgerGuard analysis submission failed:", error);
      await submitFallback();
    }
  }
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#eef2ff_0,_#f8fafc_38%,_#f8fafc_100%)] px-5 py-8 sm:px-8 sm:py-12"><div className="mx-auto max-w-3xl">
      <div className="mb-9 border-b border-slate-200 pb-8"><div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-indigo-700"><span className="h-2 w-2 rounded-full bg-indigo-600" />LedgerGuard</div><h1 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Upload documents for review</h1><p className="mt-3 max-w-2xl text-base leading-7 text-slate-600">Add an invoice and, when available, supporting documents. Analysis runs in the background while you see live progress.</p></div>
      <div className="space-y-4"><DropZone label="Primary invoice PDF" description="Required. Drag a PDF here or choose a file." file={invoice} onFileSelected={setInvoice} /><SupportingDropZone documents={supportingDocuments} onDocumentsSelected={setSupportingDocuments} onDocumentRemoved={(index) => setSupportingDocuments((documents) => documents.filter((_, documentIndex) => documentIndex !== index))} onDocumentTypeChanged={(index, documentType) => setSupportingDocuments((documents) => documents.map((document, documentIndex) => documentIndex === index ? { ...document, documentType } : document))} /></div>
      <Button className="mt-6 h-12 w-full rounded-xl bg-indigo-700 text-base shadow-lg shadow-indigo-700/20 hover:bg-indigo-800" size="lg" type="button" disabled={!invoice || isSubmitting} onClick={submit}>{isSubmitting ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : null}{isSubmitting ? "Analyzing documents..." : "Submit for analysis"}</Button>
      {message ? <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-center text-sm text-amber-900">{message}</p> : null}{analysisStatus && !report ? <ProcessingProgress status={analysisStatus} /> : null}{report ? <Report report={report} /> : null}<p className="mt-10 border-t border-slate-200 pt-6 text-center text-xs leading-5 text-slate-600">{report?.disclaimer ?? DISCLAIMER}</p>
    </div></main>
  );
}
