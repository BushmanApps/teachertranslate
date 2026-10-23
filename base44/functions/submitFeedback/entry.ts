import { createClientFromRequest } from 'npm:@base44/sdk@0.8.25';

const escapeHtml = (str) =>
  String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));

export default async function(req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { name, email, feedbackType, message, copyRequested } = await req.json();
    if (!message) {
      return Response.json({ error: 'Missing message' }, { status: 400 });
    }

    // Create feedback entity (user-scoped so RLS attributes it to the user)
    await base44.entities.Feedback.create({
      name: name || "Anonymous",
      email: email || "Not provided",
      feedback_type: feedbackType || "General",
      message,
    });

    // Send notification email to feedback inbox (service-scoped)
    await base44.asServiceRole.integrations.Core.SendEmail({
      to: "feedback@teachertranslate.com.au",
      from_name: "Teacher Translate",
      template_name: "FeedbackNotification",
      variables: {
        name: escapeHtml(name || "Anonymous"),
        email: escapeHtml(email || "Not provided"),
        feedback_type: escapeHtml(feedbackType || "General"),
        message: escapeHtml(message),
      },
    });

    // Send copy to user if requested AND email matches login email
    if (copyRequested && email && user.email && email.trim().toLowerCase() === user.email.toLowerCase()) {
      await base44.asServiceRole.integrations.Core.SendEmail({
        to: email.trim(),
        from_name: "Teacher Translate",
        template_name: "FeedbackCopy",
        variables: {
          name: escapeHtml(name || "there"),
          feedback_type: escapeHtml(feedbackType || "General"),
          message: escapeHtml(message),
        },
      });
    }

    return Response.json({ success: true });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}