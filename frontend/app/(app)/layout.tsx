import { AuthGuard } from "@/components/auth/auth-guard";
import { AppNav } from "@/components/layout/app-nav";
import { PageTransition } from "@/components/layout/page-transition";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-dvh flex-col overflow-hidden">
        <AppNav />
        <PageTransition>{children}</PageTransition>
      </div>
    </AuthGuard>
  );
}
