import './global.css';
import localFont from 'next/font/local';
import type { Metadata } from 'next';
import { ThemeProvider } from '@/components/theme';
import { SearchProvider } from '@/components/search';
import { appName } from '@/lib/shared';

// The exact faces bittensor.com ships: Haffer for text, FiraCode for
// labels/code.
const haffer = localFont({
  src: [
    { path: './fonts/Haffer-Light.ttf', weight: '300', style: 'normal' },
    { path: './fonts/Haffer-Regular.ttf', weight: '400', style: 'normal' },
    { path: './fonts/Haffer-Medium.ttf', weight: '500', style: 'normal' },
    { path: './fonts/Haffer-SemiBold.ttf', weight: '600', style: 'normal' },
  ],
  variable: '--font-haffer',
});

const firaCode = localFont({
  src: [{ path: './fonts/FiraCode-Variable.ttf', weight: '300 700', style: 'normal' }],
  variable: '--font-fira-code',
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'https://bittensor.com'),
  title: {
    template: `%s — ${appName}`,
    default: appName,
  },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html
      lang="en"
      className={`${haffer.variable} ${firaCode.variable}`}
      suppressHydrationWarning
    >
      <body className="flex flex-col min-h-screen">
        <ThemeProvider>
          <SearchProvider>{children}</SearchProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
