import Link from 'next/link';
import { TauLogo } from './logo';
import { SearchTrigger } from './search';
import { ThemeToggle } from './theme';
import { gitConfig } from '@/lib/shared';

export function Header({ children }: { children?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-40 h-14 bg-bg border-b border-line">
      <div className="relative flex h-full items-center px-5">
        {children}
        <Link href="/" className="flex items-center gap-2.5 text-fg">
          <TauLogo />
          <span className="bt-label">Bittensor Docs</span>
        </Link>
        <nav className="bt-label absolute left-1/2 -translate-x-1/2 flex items-center gap-8 font-light text-mute max-md:hidden">
          <Link href="/docs" className="hover:text-fg transition-colors">
            Docs
          </Link>
          <Link href="/docs/agents" className="hover:text-fg transition-colors">
            Agents
          </Link>
          <a
            href="https://bittensor.com"
            className="hover:text-fg transition-colors"
          >
            bittensor.com
          </a>
          <a
            href={`https://github.com/${gitConfig.user}/${gitConfig.repo}`}
            className="hover:text-fg transition-colors"
          >
            GitHub
          </a>
        </nav>
        <div className="ms-auto flex items-center gap-3">
          <SearchTrigger />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
