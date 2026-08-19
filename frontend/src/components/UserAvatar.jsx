import { useEffect, useState } from "react";

function userPhoto(user) {
  return user?.fotoUrl
    || user?.fotografiaUrl
    || user?.avatarUrl
    || user?.photoUrl
    || "";
}

function initials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)[0]}` : parts[0]?.slice(0, 2) || "U")
    .toUpperCase();
}

export function UserAvatar({ user }) {
  const photo = userPhoto(user);
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [photo]);

  return (
    <span className={`avatar ${photo && !failed ? "avatar-with-photo" : ""}`} aria-hidden="true">
      {photo && !failed
        ? <img src={photo} alt="" onError={() => setFailed(true)} />
        : initials(user?.name)}
    </span>
  );
}
