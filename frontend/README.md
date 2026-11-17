# SDN Impact Analyzer — React + Vite

This is a complete React JSX project for the SDN Impact Analyzer. It includes a drag-and-drop network topology editor, editable device properties, JSON topology import/export, impact simulation, and session history.

## Requirements

- Node.js 18 or newer (Node.js 20 LTS recommended)
- npm
- Internet access for the first dependency installation

## Run locally

1. Extract this ZIP file.
2. Open the extracted `sdn-impact-analyzer-react` folder in VS Code.
3. Open the VS Code terminal in that folder (the folder containing `package.json`).
4. Run:

   ```bash
   npm install
   npm run dev
   ```

5. Open the local URL printed by Vite, normally `http://localhost:5173`.

## Production build

```bash
npm run build
npm run preview
```

## Features

- Drag switches, routers, hosts, servers, SDN controllers, and cloud nodes onto the canvas.
- Connect devices by dragging between their connection handles.
- Move, select, configure, and delete devices.
- Save and load topology JSON files.
- Simulate switch failure, host failure, link failure, and high traffic.
- Impact analysis uses graph traversal to find devices disconnected from the remaining network.
- View analysis history for the current browser session.

## Important project scope

The impact engine is a frontend graph simulation. It does **not** start Mininet, connect to a Ryu controller, send OpenFlow messages, or measure real packet loss/latency. Those integrations require a separate backend and a running SDN environment.

## Troubleshooting

- If `npm` is not recognized, install Node.js LTS and reopen VS Code.
- If `npm install` fails, check your internet connection and run it again from the project root.
- Do not open `index.html` directly. Start the Vite development server with `npm run dev`.
- If port 5173 is already in use, Vite will print another local port; open the URL it prints.
