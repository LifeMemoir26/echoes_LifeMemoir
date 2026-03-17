"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { stripBasePath } from "@/lib/runtime/base-path";
import { useWorkspaceContext } from "@/lib/workspace/context";
import { microRebound, snappy } from "@/lib/motion/spring";

const NAV_TABS = [
  { label: "主页", href: "/" },
  { label: "采访", href: "/interview" },
] as const;

const KNOWLEDGE_ITEMS = [
  { label: "资料文件", href: "/knowledge" },
  { label: "人生事件", href: "/knowledge/events" },
  { label: "人物侧写", href: "/knowledge/profile" },
] as const;

const TIME_ITEMS = [
  { label: "时间轴", href: "/timeline" },
  { label: "回忆录", href: "/memoir" },
] as const;

function isKnowledgeActive(pathname: string) {
  return pathname.startsWith("/knowledge");
}

function isTimeActive(pathname: string) {
  return pathname === "/timeline" || pathname === "/memoir";
}

function isTabActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function AppNav() {
  const pathname = usePathname();
  const normalizedPathname = stripBasePath(pathname);
  const router = useRouter();
  const { username, logout } = useWorkspaceContext();
  const [knowledgeDropdownOpen, setKnowledgeDropdownOpen] = useState(false);
  const [timeDropdownOpen, setTimeDropdownOpen] = useState(false);
  const knowledgeDropdownRef = useRef<HTMLDivElement>(null);
  const timeDropdownRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        knowledgeDropdownRef.current &&
        !knowledgeDropdownRef.current.contains(e.target as Node)
      ) {
        setKnowledgeDropdownOpen(false);
      }
      if (
        timeDropdownRef.current &&
        !timeDropdownRef.current.contains(e.target as Node)
      ) {
        setTimeDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Close dropdowns on route change (render-time, avoids setState-in-effect)
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setKnowledgeDropdownOpen(false);
    setTimeDropdownOpen(false);
  }

  const tabClass = "relative py-1 transition-colors duration-150";

  const renderDropdown = (
    items: readonly { label: string; href: string }[],
    isOpen: boolean,
    dropdownKey: string,
  ) => (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key={dropdownKey}
          initial={{ opacity: 0, scale: 0.95, y: -4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -4 }}
          transition={snappy}
          className="absolute left-1/2 top-full mt-2 w-28 -translate-x-1/2 origin-top rounded-xl border border-black/[0.06] bg-[var(--glass-default)] py-1 shadow-[var(--shadow-perfect)] backdrop-blur-[15px] backdrop-saturate-[1.8]"
        >
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href as Route}
              className={`block px-4 py-2 text-sm transition-colors duration-100 ${
                normalizedPathname === item.href
                  ? "text-[#A2845E] font-semibold"
                  : "text-slate-600 hover:text-[#A2845E] hover:bg-[#A2845E]/[0.06]"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );

  return (
    <nav className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-[#A2845E]/[0.06] bg-[var(--glass-thick)] px-6 backdrop-blur-[20px] backdrop-saturate-[1.8] shadow-[var(--shadow-card)]">
      {/* Brand */}
      <span className="font-[var(--font-heading)] text-xl text-[#A2845E] tracking-wide select-none">
        ECHOES
      </span>

      {/* Tabs */}
      <div className="flex items-center gap-6 text-sm font-medium">
        {NAV_TABS.map((tab) => {
          const active = isTabActive(normalizedPathname, tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`${tabClass} ${active ? "text-[#A2845E]" : "text-slate-500 hover:text-slate-800"}`}
            >
              {tab.label}
              {active && (
                <motion.span
                  layoutId="nav-indicator"
                  className="absolute inset-x-0 -bottom-[1px] h-0.5 rounded-full bg-[#A2845E]"
                  transition={microRebound}
                />
              )}
            </Link>
          );
        })}

        {/* 知识库 dropdown */}
        <div ref={knowledgeDropdownRef} className="relative">
          <button
            type="button"
            onClick={() => {
              setKnowledgeDropdownOpen((v) => !v);
              setTimeDropdownOpen(false);
            }}
            className={`flex cursor-pointer items-center gap-1 ${tabClass} ${isKnowledgeActive(normalizedPathname) ? "text-[#A2845E]" : "text-slate-500 hover:text-slate-800"}`}
            aria-expanded={knowledgeDropdownOpen}
            aria-haspopup="true"
          >
            知识库
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform duration-150 ${knowledgeDropdownOpen ? "rotate-180" : ""}`}
            />
            {isKnowledgeActive(normalizedPathname) && (
              <motion.span
                layoutId="nav-indicator"
                className="absolute inset-x-0 -bottom-[1px] h-0.5 rounded-full bg-[#A2845E]"
                transition={microRebound}
              />
            )}
          </button>
          {renderDropdown(
            KNOWLEDGE_ITEMS,
            knowledgeDropdownOpen,
            "knowledge-dropdown",
          )}
        </div>

        {/* 时光 dropdown */}
        <div ref={timeDropdownRef} className="relative">
          <button
            type="button"
            onClick={() => {
              setTimeDropdownOpen((v) => !v);
              setKnowledgeDropdownOpen(false);
            }}
            className={`flex cursor-pointer items-center gap-1 ${tabClass} ${isTimeActive(normalizedPathname) ? "text-[#A2845E]" : "text-slate-500 hover:text-slate-800"}`}
            aria-expanded={timeDropdownOpen}
            aria-haspopup="true"
          >
            时光
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform duration-150 ${timeDropdownOpen ? "rotate-180" : ""}`}
            />
            {isTimeActive(normalizedPathname) && (
              <motion.span
                layoutId="nav-indicator"
                className="absolute inset-x-0 -bottom-[1px] h-0.5 rounded-full bg-[#A2845E]"
                transition={microRebound}
              />
            )}
          </button>
          {renderDropdown(TIME_ITEMS, timeDropdownOpen, "time-dropdown")}
        </div>
      </div>

      {/* User + logout */}
      <div className="flex items-center gap-3">
        {username && <span className="text-sm text-slate-500">{username}</span>}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleLogout}
          aria-label="退出登录"
        >
          退出
        </Button>
      </div>
    </nav>
  );
}
