/** Placeholder — will be replaced by the gallery + filters layout. */

export default function App() {
  return (
    <div className="flex h-screen w-full flex-col">
      <header className="h-14 shrink-0 border-b border-[--border] bg-[--surface-1] px-6 flex items-center">
        <h1 className="text-lg font-semibold tracking-tight">CutFinder</h1>
      </header>
      <main className="flex-1 overflow-auto p-6">
        <p className="text-[--text-secondary]">Loading…</p>
      </main>
    </div>
  )
}
