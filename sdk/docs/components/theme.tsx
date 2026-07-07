'use client';

import { ThemeProvider as NextThemesProvider, useTheme } from 'next-themes';
import { Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <button
      type="button"
      aria-label="Toggle theme"
      className="p-2 text-mute hover:text-fg transition-colors"
      onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
    >
      {mounted && resolvedTheme === 'dark' ? (
        <Moon className="size-3.5" />
      ) : (
        <Sun className="size-3.5" />
      )}
    </button>
  );
}
