const API_HOST = process.env.NEXT_PUBLIC_API_HOST || "http://localhost:5000";

export interface ChatResponse {
  answer: string;
  images: Array<{
    image_path: string;
    label?: string;
    metadata?: Record<string, any>;
  }>;
}

export async function sendChatMessage(question: string): Promise<ChatResponse> {
  const response = await fetch(`${API_HOST}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  return await response.json();
}
