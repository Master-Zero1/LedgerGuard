"use client";

import { CheckCircle2, FileText, LoaderCircle, ShieldCheck, UploadCloud } from "lucide-react";
import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const API_URL = "http://localhost:8000/upload";
const DISCLAIMER = "LedgerGuard provides informational analysis, not legal or financial advice.";

type Evidence = { record_id: string; page_ref: string; excerpt: string };
type ReportItem = { candidate_id: string; discrepancy_type: string; dollar_impact: string; confidence_score: number | null; evidence: Evidence[] };
type ReportPayload = {
  disclaimer?: string;
  summary: { confirmed_discrepancy_count: number; total_confirmed_dollar_impact: string };
  confirmed_discrepancies: ReportItem[];
  dismissed_items: ReportItem[];
};
type DropZoneProps = { label: string; description: string; file: File | null; onFileSelected: (file: File | null) => void };
type SupportingDropZoneProps = { files: File[]; onFilesSelected: (files: File[]) => void; onFileRemoved: (index: number) => void };

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

function SupportingDropZone({ files, onFilesSelected, onFileRemoved }: SupportingDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function addFiles(fileList: FileList | null) {
    const incoming = Array.from(fileList ?? []).filter(isPdf);
    if (!incoming.length) return;
    onFilesSelected([...files, ...incoming]);
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
      <Button className="mt-4 rounded-lg border-slate-200" variant="outline" type="button" onClick={() => inputRef.current?.click()}>{files.length ? "Add another PDF" : "Choose PDFs"}</Button>
      {files.length ? (
        <ul className="mx-auto mt-5 max-w-xl space-y-2 text-left">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.lastModified}-${index}`} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <span className="flex min-w-0 items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-indigo-600" aria-hidden="true" /><span className="truncate font-medium">{file.name}</span></span>
              <button className="shrink-0 text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-slate-900" type="button" onClick={() => onFileRemoved(index)}>Remove</button>
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

function DiscrepancyCard({ item }: { item: ReportItem }) {
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
        <Accordion type="single" collapsible><AccordionItem value="evidence" className="border-b-0"><AccordionTrigger className="py-4 text-sm font-semibold text-slate-800 hover:no-underline">View evidence citations</AccordionTrigger><AccordionContent className="pb-1"><EvidenceList evidence={item.evidence} /></AccordionContent></AccordionItem></Accordion>
      </CardContent>
    </Card>
  );
}

function Report({ report }: { report: ReportPayload }) {
  const confirmed = useMemo(() => [...report.confirmed_discrepancies].sort((left, right) => Number(right.dollar_impact) - Number(left.dollar_impact)), [report.confirmed_discrepancies]);
  const dismissed = useMemo(() => [...report.dismissed_items].sort((left, right) => Number(right.dollar_impact) - Number(left.dollar_impact)), [report.dismissed_items]);
  return (
    <section className="mt-10 space-y-8" aria-live="polite">
      <Card className="overflow-hidden border-0 bg-slate-950 text-white shadow-[0_20px_55px_rgb(15,23,42,0.24)]">
        <CardHeader className="relative gap-6 p-6 sm:p-8"><div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-indigo-500/20 blur-3xl" aria-hidden="true" />
          <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between"><div><div className="flex items-center gap-2 text-sm font-medium text-indigo-200"><ShieldCheck className="h-4 w-4" aria-hidden="true" />Analysis complete</div><p className="mt-5 text-sm font-medium text-slate-300">Total confirmed impact</p><CardTitle className="mt-1 text-5xl font-semibold tracking-tight text-white">{money(report.summary.total_confirmed_dollar_impact)}</CardTitle></div><div className="border-t border-white/15 pt-4 sm:border-l sm:border-t-0 sm:pl-7 sm:pt-0"><p className="text-2xl font-semibold text-white">{report.summary.confirmed_discrepancy_count}</p><p className="mt-1 max-w-32 text-sm leading-5 text-slate-300">confirmed {report.summary.confirmed_discrepancy_count === 1 ? "finding" : "findings"} requiring review</p></div></div>
        </CardHeader>
      </Card>
      <div><div className="flex items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Review queue</p><h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Confirmed discrepancies</h2></div><p className="hidden text-sm text-slate-500 sm:block">Ranked by dollar impact</p></div><div className="mt-5 space-y-4">{confirmed.length ? confirmed.map((item) => <DiscrepancyCard key={item.candidate_id} item={item} />) : <p className="text-sm text-slate-600">No confirmed discrepancies were found.</p>}</div></div>
      {dismissed.length ? <Card className="border-slate-200 bg-slate-50/80 text-slate-600 shadow-none"><CardContent className="p-5 pt-0 sm:p-6 sm:pt-0"><Accordion type="single" collapsible><AccordionItem value="dismissed" className="border-b-0"><AccordionTrigger className="text-slate-700 hover:no-underline"><span className="flex items-center gap-2"><span className="rounded-full bg-slate-200 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Not counted</span> Considered items ({dismissed.length})</span></AccordionTrigger><AccordionContent><p className="mb-4 text-sm text-slate-500">These findings were reviewed and do not contribute to the confirmed total.</p><div className="space-y-4">{dismissed.map((item) => <div key={item.candidate_id} className="rounded-xl border border-slate-200 bg-white p-4"><div className="flex justify-between gap-4 text-sm"><span className="font-medium">{titleCase(item.discrepancy_type)}</span><span>{money(item.dollar_impact)}</span></div><p className="mt-2 text-xs text-slate-500">Dismissed items do not contribute to the total confirmed impact.</p><div className="mt-3"><EvidenceList evidence={item.evidence} /></div></div>)}</div></AccordionContent></AccordionItem></Accordion></CardContent></Card> : null}
    </section>
  );
}

export default function UploadPage() {
  const [invoice, setInvoice] = useState<File | null>(null);
  const [supportingFiles, setSupportingFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [report, setReport] = useState<ReportPayload | null>(null);
  async function submit() {
    if (!invoice || isSubmitting) return;
    setIsSubmitting(true); setMessage(null); setReport(null);
    const body = new FormData(); body.append("file", invoice); body.append("document_type", "invoice");
    supportingFiles.forEach((supportingFile) => {
      body.append("supporting_files", supportingFile);
      body.append("supporting_document_types", "contract");
    });
    try { const response = await fetch(API_URL, { method: "POST", body }); const payload: unknown = await response.json(); if (!response.ok) { console.error("LedgerGuard upload failed:", payload); setMessage("The upload could not be processed. Check the browser console for the API response."); return; } setReport(payload as ReportPayload); }
    catch (error) { console.error("LedgerGuard upload request failed:", error); setMessage("The API could not be reached. Make sure it is running on localhost:8000."); }
    finally { setIsSubmitting(false); }
  }
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#eef2ff_0,_#f8fafc_38%,_#f8fafc_100%)] px-5 py-8 sm:px-8 sm:py-12"><div className="mx-auto max-w-3xl">
      <div className="mb-9 border-b border-slate-200 pb-8"><div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-indigo-700"><span className="h-2 w-2 rounded-full bg-indigo-600" />LedgerGuard</div><h1 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Upload documents for review</h1><p className="mt-3 max-w-2xl text-base leading-7 text-slate-600">Add an invoice and, when available, the supporting contract. Analysis runs synchronously and can take several seconds.</p></div>
      <div className="space-y-4"><DropZone label="Primary invoice PDF" description="Required. Drag a PDF here or choose a file." file={invoice} onFileSelected={setInvoice} /><SupportingDropZone files={supportingFiles} onFilesSelected={setSupportingFiles} onFileRemoved={(index) => setSupportingFiles((files) => files.filter((_, fileIndex) => fileIndex !== index))} /></div>
      <Button className="mt-6 h-12 w-full rounded-xl bg-indigo-700 text-base shadow-lg shadow-indigo-700/20 hover:bg-indigo-800" size="lg" type="button" disabled={!invoice || isSubmitting} onClick={submit}>{isSubmitting ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : null}{isSubmitting ? "Analyzing documents..." : "Submit for analysis"}</Button>
      {message ? <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-center text-sm text-amber-900">{message}</p> : null}{report ? <Report report={report} /> : null}<p className="mt-10 border-t border-slate-200 pt-6 text-center text-xs leading-5 text-slate-600">{report?.disclaimer ?? DISCLAIMER}</p>
    </div></main>
  );
}
