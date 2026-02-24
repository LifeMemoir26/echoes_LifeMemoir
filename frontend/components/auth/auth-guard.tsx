"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useWorkspaceContext } from "@/lib/workspace/context";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useWorkspaceContext();
  const router = useRouter();
  // Delay render until after client-side hydration so token can be read from localStorage
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isAuthenticated) {
      router.replace("/login");
    }
  }, [mounted, isAuthenticated, router]);

  if (!mounted) return null;
  if (!isAuthenticated) return null;

  return <>{children}</>;
}
