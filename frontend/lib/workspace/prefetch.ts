export type PrefetchTask<T> = () => Promise<T>;

export async function runWithConcurrencyLimit<T>(tasks: Array<PrefetchTask<T>>, limit: number): Promise<T[]> {
  const cap = Math.max(1, Math.floor(limit));
  const results: T[] = [];
  const executing = new Set<Promise<void>>();

  for (const task of tasks) {
    const runner = (async () => {
      const value = await task();
      results.push(value);
    })();

    executing.add(runner);
    void runner.finally(() => {
      executing.delete(runner);
    });

    if (executing.size >= cap) {
      await Promise.race(executing);
    }
  }

  await Promise.all(executing);
  return results;
}
