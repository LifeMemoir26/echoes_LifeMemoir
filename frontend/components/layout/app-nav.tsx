"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkspaceContext } from "@/lib/workspace/context";

const NAV_TABS = [
  { label: "主页", href: "/" },
  { label: "知识库", href: "/knowledge" },
  { label: "采访", href: "/interview" }
] as const;

const TIME_ITEMS = [
  { label: "时间轴", href: "/timeline" },
  { label: "回忆录", href: "/memoir" }
] as const;

function isTimeActive(pathname: string) {
  return pathname === "/timeline" || pathname === "/memoir";
}

function isTabActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { username, logout } = useWorkspaceContext();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Close dropdown on route change
  useEffect(() => {
    setDropdownOpen(false);
  }, [pathname]);

  const activeTabClass = "text-[#A2845E] border-b-2 border-[#A2845E] pb-[2px]";
  const inactiveTabClass = "text-slate-500 hover:text-slate-800 transition-colors duration-150";

  return (
    <nav className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-black/[0.06] bg-white/80 px-6 backdrop-blur-md">
      {/* Brand */}
      <span className="font-[var(--font-heading)] text-xl text-[#A2845E] tracking-wide select-none">
        ECHOES
      </span>

      {/* Tabs */}
      <div className="flex items-center gap-6 text-sm font-medium">
        {NAV_TABS.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={isTabActive(pathname, tab.href) ? activeTabClass : inactiveTabClass}
          >
            {tab.label}
          </Link>
        ))}

        {/* 时光 dropdown */}
        <div ref={dropdownRef} className="relative">
          <button
            type="button"
            onClick={() => setDropdownOpen((v) => !v)}
            className={`flex items-center gap-1 ${isTimeActive(pathname) ? activeTabClass : inactiveTabClass}`}
            aria-expanded={dropdownOpen}
            aria-haspopup="true"
          >
            时光
            <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-150 ${dropdownOpen ? "rotate-180" : ""}`} />
          </button>

          <AnimatePresence>
            {dropdownOpen && (
              <motion.div
                key="time-dropdown"
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.15 }}
                className="absolute left-1/2 top-full mt-2 w-28 -translate-x-1/2 rounded-xl border border-black/[0.06] bg-white/90 py-1 shadow-lg backdrop-blur-sm"
              >
                {TIME_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`block px-4 py-2 text-sm transition-colors duration-100 ${
                      pathname === item.href
                        ? "text-[#A2845E] font-semibold"
                        : "text-slate-600 hover:text-[#A2845E] hover:bg-[#F5EDE4]"
                    }`}
                  >
                    {item.label}
                  </Link>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* User + logout */}
      <div className="flex items-center gap-3">
        {username && (
          <span className="text-sm text-slate-500">{username}</span>
        )}
        <Button variant="ghost" size="sm" onClick={handleLogout} aria-label="退出登录">
          退出
        </Button>
      </div>
    </nav>
  );
}
