import { createClientFromRequest } from 'npm:@base44/sdk@0.8.25';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { fileUrl } = await req.json();

    if (!fileUrl) {
      return Response.json({ error: 'Missing fileUrl' }, { status: 400 });
    }

    const result = await base44.asServiceRole.integrations.Core.InvokeLLM({
      prompt: `Extract all visible text from this school report. Include teacher comments, subject headings, and written feedback. Preserve subject structure.

REDACTIONS: Blacked-out or greyed-out areas are redactions for privacy. SKIP them instantly — do not read, guess, or reconstruct hidden content. Continue extracting the visible text around redactions. Return only extracted text.`,
      file_urls: [fileUrl],
      model: "gemini_3_flash"
    });

    return Response.json({ success: true, text: result });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});