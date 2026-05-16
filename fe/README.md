# Biology RAG Frontend

This is a Next.js frontend for the Biology RAG (Retrieval-Augmented Generation) system. It provides a chat interface to interact with the RAG backend, including support for retrieving and displaying biological diagrams and images.

## Environment Setup

Create a `.env.local` file (or set environment variables) with the following:

```env
NEXT_PUBLIC_API_HOST=http://localhost:5000
```

## Getting Started

### Installation
```bash
npm install
```

### Running Locally
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) with your browser.

### Running on Google Colab
If you are running this frontend alongside the backend in a Colab notebook:

1. Use the special Colab script to bind to all interfaces:
   ```bash
   npm run colab
   ```

2. Expose the port in your notebook:
   ```python
   from google.colab import output
   output.serve_kernel_port_as_window(3000)
   ```

## Features
- Modern, responsive chat interface.
- Support for markdown and bold text highlighting.
- Integrated image gallery for retrieved biological diagrams.
- Cross-platform path handling for Windows and Linux environments.
- Proxy rewrites for seamless image serving from the backend.
