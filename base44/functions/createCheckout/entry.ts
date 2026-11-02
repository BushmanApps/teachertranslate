export default async function() {
  return Response.json(
    { error: 'Subscriptions are purchased through the Teacher Translate iPhone or Android app.' },
    { status: 410 }
  );
}
