"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { useWorkspaceContext } from "@/lib/workspace/context";

const emptySubscribe = () => () => {};

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { authReady, isAuthenticated } = useWorkspaceContext();
  const router = useRouter();
  // Returns false during SSR, true on client — avoids hydration mismatch without setState-in-effect
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  useEffect(() => {
    if (authReady && !isAuthenticated) {
      router.replace("/login");
    }
  }, [authReady, isAuthenticated, router]);

  if (!mounted) return null;
  if (!authReady) return null;
  if (!isAuthenticated) return null;

  return <>{children}</>;
}
