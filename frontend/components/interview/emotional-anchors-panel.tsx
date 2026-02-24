"use client";

interface Props {
  positiveTriggers: string[];
  sensitiveTopics: string[];
}

export function EmotionalAnchorsPanel({ positiveTriggers, sensitiveTopics }: Props) {
  const isEmpty = positiveTriggers.length === 0 && sensitiveTopics.length === 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      <p className="mb-3 shrink-0 panel-label">情感锚点</p>
      {isEmpty ? (
        <div className="flex flex-1 items-center justify-center text-sm italic text-slate-400 text-center px-4">
          开始采访，发送几条消息后辅助内容将自动出现
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto mask-fade-b pt-1 pb-6">
          <div className="space-y-5">
            {/* Positive triggers */}
            <div>
              <p className="text-xs font-medium text-[#6B8E6B] mb-2 tracking-wide">积极触发点</p>
              {positiveTriggers.length === 0 ? (
                <p className="text-xs italic text-slate-400">暂无</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {positiveTriggers.map((tag, i) => (
                    <span
                      key={i}
                      className="inline-block rounded-full bg-[#F0F5F0] border border-[#6B8E6B]/20 text-[#4A6B4A] text-xs px-2.5 py-0.5 transition-colors duration-150 hover:border-[#6B8E6B]/40"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            {/* Sensitive topics */}
            <div>
              <p className="text-xs font-medium text-[#B07A7A] mb-2 tracking-wide">敏感话题</p>
              {sensitiveTopics.length === 0 ? (
                <p className="text-xs italic text-slate-400">暂无</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {sensitiveTopics.map((tag, i) => (
                    <span
                      key={i}
                      className="inline-block rounded-full bg-[#FDF2F2] border border-[#B07A7A]/20 text-[#8B5A5A] text-xs px-2.5 py-0.5 transition-colors duration-150 hover:border-[#B07A7A]/40"
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
