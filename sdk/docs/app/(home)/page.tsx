import Link from 'next/link';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { TauLogo } from '@/components/logo';

async function catalogCounts() {
  const dir = path.join(process.cwd(), 'public/catalog');
  const [intents, reads, errors] = await Promise.all([
    readFile(path.join(dir, 'intents.json'), 'utf8'),
    readFile(path.join(dir, 'reads.json'), 'utf8'),
    readFile(path.join(dir, 'errors.json'), 'utf8'),
  ]);
  return {
    tx: JSON.parse(intents).length as number,
    query: JSON.parse(reads).length as number,
    errors: Object.keys(JSON.parse(errors).codes).length,
  };
}

export default async function HomePage() {
  const counts = await catalogCounts();
  const stats = [
    { value: counts.tx, label: 'Transactions', href: '/docs/tx' },
    { value: counts.query, label: 'Queries', href: '/docs/query' },
    { value: counts.errors, label: 'Error codes', href: '/docs/errors' },
  ];

  return (
    <div className="relative flex flex-col justify-center items-center text-center flex-1 gap-8 overflow-hidden px-4 py-24">
      <TauLogo className="pointer-events-none absolute top-1/2 left-1/2 size-[36rem] -translate-x-1/2 -translate-y-1/2 opacity-[0.025]" />

      <p className="bt-label text-mute">The chain, documented for agents</p>
      <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
        Bittensor Documentation
      </h1>
      <p className="max-w-xl text-sm leading-relaxed text-mute">
        Do anything on the Bittensor chain with the subtensor SDK and CLI.
        Every operation, every query, every error — generated from the chain
        itself and designed for agents and humans alike.
      </p>

      <div className="flex gap-6">
        <Link href="/docs" className="bt-label underline underline-offset-4">
          Read the docs
        </Link>
        <Link href="/docs/agents" className="bt-label underline underline-offset-4">
          For agents
        </Link>
        <Link href="/docs/quickstart" className="bt-label underline underline-offset-4">
          Quickstart
        </Link>
      </div>

      <div className="mt-12 flex divide-x divide-line border border-line">
        {stats.map((stat) => (
          <Link
            key={stat.label}
            href={stat.href}
            className="flex flex-col gap-1 px-10 py-6 transition-colors hover:bg-hover"
          >
            <span className="font-mono text-2xl">{stat.value}</span>
            <span className="bt-label text-mute">{stat.label}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
