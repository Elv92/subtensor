import { TauLogo } from './logo';
import { gitConfig } from '@/lib/shared';

const links = [
  { label: 'bittensor.com', href: 'https://bittensor.com' },
  { label: 'Discord', href: 'https://discord.gg/bittensor' },
  { label: 'X', href: 'https://x.com/bittensor_' },
  { label: 'GitHub', href: `https://github.com/${gitConfig.user}/${gitConfig.repo}` },
];

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex w-full max-w-[90rem] items-center justify-between px-5 py-8">
        <span className="flex items-center gap-2.5 text-mute">
          <TauLogo className="size-4" />
          <span className="bt-label">Bittensor</span>
        </span>
        <nav className="bt-label flex items-center gap-6 text-mute">
          {links.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="hover:text-fg transition-colors"
            >
              {link.label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  );
}
