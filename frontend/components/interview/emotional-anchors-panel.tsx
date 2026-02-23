"use client";

interface Props {
  positiveTriggers: string[];
  sensitiveTopics: string[];
}

export function EmotionalAnchorsPanel({ positiveTriggers, sensitiveTopics }: Props) {
  const isEmpty = positiveTriggers.length === 0 && sensitiveTopics.length === 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      <p className="mb-3 shrink-0 text-xs uppercase tracking-[0.16em] text-[#A2845E]">情感锚点</p>
      {isEmpty ? (
        <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted-fg)] text-center px-4">
          开始采访，发送几条消息后辅助内容将自动出现
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-medium text-emerald-700 mb-2">积极触发点</p>
              {positiveTriggers.length === 0 ? (
                <p className="text-xs text-[var(--muted-fg)]">暂无</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {positiveTriggers.map((tag, i) => (
                    <span
                      key={i}
                      className="inline-block rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs px-2 py-0.5"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-rose-700 mb-2">敏感话题</p>
              {sensitiveTopics.length === 0 ? (
                <p className="text-xs text-[var(--muted-fg)]">暂无</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {sensitiveTopics.map((tag, i) => (
                    <span
                      key={i}
                      className="inline-block rounded-full bg-rose-50 border border-rose-200 text-rose-800 text-xs px-2 py-0.5"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
