import { forwardToBackend } from '@/lib/local-backend.mjs';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function handle(request, context) {
  const { path } = await context.params;
  return forwardToBackend(request, path);
}

export const GET = handle;
export const POST = handle;
