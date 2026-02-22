import { AuthGuard } from "@/components/auth/auth-guard";
import { AppNav } from "@/components/layout/app-nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <AppNav />
      {children}
    </AuthGuard>
  );
}
