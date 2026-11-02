package com.hiremate.interview;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

class InterviewAssignmentMigrationTests extends IntegrationTest {

    @Autowired
    private DataSource dataSource;

    @Test
    @DisplayName("기존 공통 배정은 전형 설정으로 옮기고 서로 다른 배정과 개인 기록은 그대로 보존한다")
    void migrationPreservesRecordedAssignmentsAndBackfillsCommonPanels() throws Exception {
        String schema = "assignment_migration_" + UUID.randomUUID().toString().replace("-", "");
        try (Connection connection = dataSource.getConnection();
                Statement sql = connection.createStatement()) {
            sql.execute("CREATE SCHEMA " + schema);
            try {
                sql.execute("SET search_path TO " + schema);
                sql.execute("CREATE TABLE companies (id UUID PRIMARY KEY)");
                sql.execute("CREATE TABLE stages (id UUID PRIMARY KEY)");
                sql.execute("CREATE TABLE members (id UUID PRIMARY KEY)");
                sql.execute("CREATE TABLE stage_candidates (stage_id UUID, application_id UUID, company_id UUID)");
                sql.execute("CREATE TABLE interview_sessions (stage_id UUID, application_id UUID, company_id UUID, "
                        + "hr_member_id UUID, practical_member_id UUID, hr_memo TEXT DEFAULT '', "
                        + "status VARCHAR(16) DEFAULT 'SCHEDULED', PRIMARY KEY (stage_id, application_id))");
                sql.execute("INSERT INTO companies VALUES ('00000000-0000-0000-0000-000000000001')");
                sql.execute("INSERT INTO stages VALUES ('00000000-0000-0000-0000-000000000002'), "
                        + "('00000000-0000-0000-0000-000000000003')");
                sql.execute("INSERT INTO members VALUES ('00000000-0000-0000-0000-000000000004'), "
                        + "('00000000-0000-0000-0000-000000000005')");
                sql.execute("INSERT INTO stage_candidates VALUES "
                        + "('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000006', "
                        + "'00000000-0000-0000-0000-000000000001'), "
                        + "('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000007', "
                        + "'00000000-0000-0000-0000-000000000001')");
                sql.execute("INSERT INTO interview_sessions VALUES "
                        + "('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000006', "
                        + "'00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004', "
                        + "'00000000-0000-0000-0000-000000000005', 'PRIVATE-NOTE', 'ENDED'), "
                        + "('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000006', "
                        + "'00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004', "
                        + "'00000000-0000-0000-0000-000000000005', 'LEGACY-ONE', 'ENDED'), "
                        + "('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000007', "
                        + "'00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000005', "
                        + "'00000000-0000-0000-0000-000000000004', 'LEGACY-TWO', 'ENDED')");

                ScriptUtils.executeSqlScript(connection,
                        new ClassPathResource("db/migration/V42__assign_interviewers_by_stage.sql"));

                try (ResultSet assignments = sql.executeQuery("SELECT stage_id FROM interview_stage_assignments")) {
                    assertThat(assignments.next()).isTrue();
                    assertThat(assignments.getString(1)).isEqualTo("00000000-0000-0000-0000-000000000002");
                    assertThat(assignments.next()).isFalse();
                }
                try (ResultSet sessions = sql.executeQuery("SELECT status, hr_memo FROM interview_sessions "
                        + "WHERE stage_id = '00000000-0000-0000-0000-000000000002' ORDER BY application_id")) {
                    assertThat(sessions.next()).isTrue();
                    assertThat(sessions.getString(1)).isEqualTo("ENDED");
                    assertThat(sessions.getString(2)).isEqualTo("PRIVATE-NOTE");
                    assertThat(sessions.next()).isTrue();
                    assertThat(sessions.getString(1)).isEqualTo("SCHEDULED");
                    assertThat(sessions.next()).isFalse();
                }
                try (ResultSet legacy = sql.executeQuery("SELECT hr_memo FROM interview_sessions "
                        + "WHERE stage_id = '00000000-0000-0000-0000-000000000003' ORDER BY application_id")) {
                    assertThat(legacy.next()).isTrue();
                    assertThat(legacy.getString(1)).isEqualTo("LEGACY-ONE");
                    assertThat(legacy.next()).isTrue();
                    assertThat(legacy.getString(1)).isEqualTo("LEGACY-TWO");
                }
            } finally {
                sql.execute("SET search_path TO public");
                sql.execute("DROP SCHEMA " + schema + " CASCADE");
            }
        }
    }

    @Test
    @DisplayName("공유 기록 삭제 마이그레이션은 개인 메모와 면접관 의견을 유지한다")
    void sharedNoteRemovalPreservesPrivateMemosAndOpinions() throws Exception {
        String schema = "shared_note_removal_" + UUID.randomUUID().toString().replace("-", "");
        try (Connection connection = dataSource.getConnection();
                Statement sql = connection.createStatement()) {
            sql.execute("CREATE SCHEMA " + schema);
            try {
                sql.execute("SET search_path TO " + schema);
                sql.execute("CREATE TABLE interview_sessions (hr_memo TEXT, practical_memo TEXT)");
                sql.execute("INSERT INTO interview_sessions VALUES ('PRIVATE-HR', 'PRIVATE-PRACTICAL')");
                sql.execute("CREATE TABLE interview_opinions (comment TEXT)");
                sql.execute("INSERT INTO interview_opinions VALUES ('OPINION')");
                sql.execute("CREATE TABLE interview_shared_notes (text TEXT)");
                sql.execute("INSERT INTO interview_shared_notes VALUES ('OLD-SHARED-NOTE')");
                ScriptUtils.executeSqlScript(connection,
                        new ClassPathResource("db/migration/V45__remove_interview_shared_notes.sql"));
                try (ResultSet table = sql.executeQuery("SELECT to_regclass('interview_shared_notes')")) {
                    assertThat(table.next()).isTrue();
                    assertThat(table.getString(1)).isNull();
                }
                try (ResultSet memo = sql.executeQuery("SELECT hr_memo, practical_memo FROM interview_sessions")) {
                    assertThat(memo.next()).isTrue();
                    assertThat(memo.getString(1)).isEqualTo("PRIVATE-HR");
                    assertThat(memo.getString(2)).isEqualTo("PRIVATE-PRACTICAL");
                }
                try (ResultSet opinion = sql.executeQuery("SELECT comment FROM interview_opinions")) {
                    assertThat(opinion.next()).isTrue();
                    assertThat(opinion.getString(1)).isEqualTo("OPINION");
                }
            } finally {
                sql.execute("SET search_path TO public");
                sql.execute("DROP SCHEMA " + schema + " CASCADE");
            }
        }
    }

}
