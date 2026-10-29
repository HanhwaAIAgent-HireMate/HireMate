package com.hiremate.screening.domain;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TabSelectionRepository extends JpaRepository<TabSelection, TabSelection.Key> {

    List<TabSelection> findByTabIdOrderBySelectedAt(UUID tabId);

    List<TabSelection> findByTabIdIn(Collection<UUID> tabIds);
}
