import { source } from '@/lib/source';
import { serializeTree } from '@/lib/tree';
import { Header } from '@/components/header';
import { Footer } from '@/components/footer';
import { Sidebar, SidebarProvider, SidebarTrigger } from '@/components/sidebar';

export default function Layout({ children }: LayoutProps<'/docs'>) {
  const tree = serializeTree(source.getPageTree());

  return (
    <SidebarProvider>
      <Header>
        <SidebarTrigger />
      </Header>
      <div className="mx-auto flex w-full max-w-[90rem] flex-1 px-5">
        <Sidebar tree={tree} />
        {children}
      </div>
      <Footer />
    </SidebarProvider>
  );
}
