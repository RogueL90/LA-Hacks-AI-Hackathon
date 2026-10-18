import { Navigate, Route, Routes } from "react-router-dom";
import { SpaceView } from "./routes/SpaceView";

export default function App() {
  return (
    <Routes>
      <Route path="/s/:spaceId" element={<SpaceView />} />
      {/* Until there is a landing page, open the prebuilt demo home. */}
      <Route path="*" element={<Navigate to="/s/demo_home_01" replace />} />
    </Routes>
  );
}
