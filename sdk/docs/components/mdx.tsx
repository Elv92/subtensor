import Link from 'next/link';
import type { MDXComponents } from 'mdx/types';
import type { ComponentProps, ReactNode } from 'react';
import { CopyCodeButton } from './copy';
import { cn } from '@/lib/cn';

function heading(Tag: 'h2' | 'h3' | 'h4') {
  return function Heading({ id, children, ...props }: ComponentProps<typeof Tag>) {
    if (!id) return <Tag {...props}>{children}</Tag>;
    return (
      <Tag id={id} {...props}>
        <a href={`#${id}`}>{children}</a>
      </Tag>
    );
  };
}

function Anchor({ href, ...props }: ComponentProps<'a'>) {
  if (href && href.startsWith('/')) {
    return <Link href={href} {...props} />;
  }
  return <a href={href} {...props} />;
}

function Pre(props: ComponentProps<'pre'>) {
  return (
    <div className="bt-codeblock">
      <pre {...props} />
      <CopyCodeButton />
    </div>
  );
}

export function Cards({ children }: { children: ReactNode }) {
  return <div className="grid gap-px sm:grid-cols-2 border border-line bg-line not-prose my-6">{children}</div>;
}

export function Card({
  title,
  description,
  href,
}: {
  title: string;
  description?: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        'block bg-bg p-5 transition-colors hover:bg-panel',
      )}
    >
      <p className="bt-label mb-2">{title}</p>
      {description && (
        <p className="text-[0.8125rem] leading-relaxed text-mute">{description}</p>
      )}
    </Link>
  );
}

export function getMDXComponents(components?: MDXComponents) {
  return {
    h2: heading('h2'),
    h3: heading('h3'),
    h4: heading('h4'),
    a: Anchor,
    pre: Pre,
    Cards,
    Card,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
