import { AuthGuard } from "@/components/auth/auth-guard";
import { AppNav } from "@/components/layout/app-nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-dvh flex-col overflow-hidden">
        <AppNav />
        <div className="flex-1 overflow-auto">{children}</div>
      </div>
    </AuthGuard>
  );
}
