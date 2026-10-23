import { createClientFromRequest } from 'npm:@base44/sdk@0.8.25';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Pro-only feature: verify subscription server-side
    const svc = base44.asServiceRole;
    const byOwner = await svc.entities.UserProfile.filter({ created_by_id: user.id });
    const byEmail = await svc.entities.UserProfile.filter({ email: user.email });
    if (![...(byOwner || []), ...(byEmail || [])].some((p) => p.is_subscribed || p.lifetime_pro)) {
      return Response.json({ error: 'Pro subscription required' }, { status: 402 });
    }

    const { plainText, studentYear, studentName, mode } = await req.json();

    if (!plainText || !studentYear) {
      return Response.json({ error: 'Missing plainText or studentYear' }, { status: 400 });
    }

    const studentRef = studentName || "the student";
    const isHilarious = mode === "hilarious";

    const stylePrompt = isHilarious
      ? `You are an expert at writing school reports in the diplomatic, carefully-worded "teacher speak" style that Australian teachers use — but CRANKED UP TO ELEVEN for comedic effect.

This language is characteristically:
- Absurdly positive in framing even when delivering obvious criticism — so upbeat it's clearly a parody
- Overflowing with ridiculous phrases like "is on an exciting journey towards", "is blossoming beautifully into", "shows magnificent potential to one day perhaps", "continues to explore the rich tapestry of", "is navigating the landscape of"
- Avoids ALL direct negative statements, softens everything with delightfully excessive hedging like "on the rarest of occasions", "in those special moments when", "from time to time, as we all do", "when the stars align"
- Uses so much flowery, diplomatic language that the actual message becomes hilariously buried under positivity
- Maintains professional distance while sounding impossibly warm and cheerfully detached
- Should be genuinely funny — like a parody of the most over-the-top, heavily-workshopped teacher report ever written
- Sprinkle in dry Australian understatement and gentle sarcasm

Make it sound like a teacher who has attended WAY too many "positive framing" professional development sessions and has completely lost the ability to say anything directly. The result should be so diplomatically overwrought and absurdly cheerful that it's clearly a comedy version — the blunter the original message, the more ridiculously positive the teacher-speak should become.`
      : `You are an expert at writing school reports in the diplomatic, carefully-worded "teacher speak" style that Australian teachers use.

This language is characteristically:
- Positive in framing even when delivering criticism
- Full of phrases like "is developing", "is beginning to", "would benefit from", "shows potential to", "continues to work towards"
- Avoids direct negative statements, always softens concerns with "at times", "on occasion", "can sometimes"
- Uses hedging language and qualifiers
- Maintains professional distance while sounding warm`;

    const prompt = `${stylePrompt}

IMPORTANT: Use Australian English spelling in ALL output (e.g. "colour" not "color", "organise" not "organize", "centre" not "center", "behaviour" not "behavior", "favourite" not "favorite", "practise" as verb / "practice" as noun, "programme" not "program" unless referring to software).

Student: ${studentRef}
Year Level: ${studentYear}

PLAIN ENGLISH TEXT TO CONVERT:
"""
${plainText}
"""

Convert this into a message FROM the parent TO the teacher that politely requests the teacher's assistance to help facilitate what the parent is asking for. The message must be written in authentic Australian school "teacher speak"${isHilarious ? " — make it hilariously over-the-top and absurdly positive" : ""} and must clearly ask the teacher for their support, guidance, or action to help make this happen for ${studentRef}.

IMPORTANT: The output is a request to the teacher — it must ask for their help (e.g. "we were hoping you might be able to support...", "could we kindly ask for your assistance with...", "we'd greatly appreciate your guidance in...") rather than just restating the concern in teacher-speak.

Return JSON with:
{
  "teacher_talk": "The converted teacher-speak message requesting the teacher's assistance",
  "translation_notes": "Brief note explaining the key diplomatic phrases used and what they really mean"
}`;

    const result = await base44.asServiceRole.integrations.Core.InvokeLLM({
      prompt,
      response_json_schema: {
        type: "object",
        properties: {
          teacher_talk: { type: "string" },
          translation_notes: { type: "string" }
        }
      }
    });

    return Response.json({ success: true, result });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});