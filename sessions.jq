[group_by(.sessionId // "no-session")[]
 | select(.[0].sessionId != null)
 | {
     session_id: .[0].sessionId,
     topic: (.[0].display | .[0:60]),
     folder: (.[0].project | split("/") | last),
     project: .[0].project,
     date: (.[0].timestamp / 1000 | strftime("%Y-%m-%d %H:%M")),
     messages: length
   }
] | sort_by(.date) | reverse
