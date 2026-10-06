export function WorkspaceLoading({ label = "Carregando UNI Workspace..." }: { label?: string }) {
  return (
    <main className="workspace-surface min-h-screen p-6 sm:p-10" aria-busy="true" aria-label={label}>
      <div className="mx-auto max-w-7xl space-y-8">
        <div className="flex items-center gap-3">
          <div className="skeleton h-11 w-11" />
          <div className="space-y-2"><div className="skeleton h-4 w-36" /><div className="skeleton h-3 w-52" /></div>
        </div>
        <p role="status" className="text-sm text-slate-600">{label}</p>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
          {Array.from({ length: 4 }, (_, index) => <div key={index} className="skeleton h-32" />)}
        </div>
        <div className="skeleton h-80" aria-hidden="true" />
      </div>
    </main>
  );
}
