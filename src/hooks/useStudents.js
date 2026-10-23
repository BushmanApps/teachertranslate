import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { base44 } from "@/api/base44Client";

const ACTIVE_KEY = "tt_active_student_id";
const getStoredActiveId = () => {
  try { return localStorage.getItem(ACTIVE_KEY); } catch { return null; }
};
const storeActiveId = (id) => {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {}
};

export function useStudents(currentUser) {
  const queryClient = useQueryClient();
  const [activeStudent, setActiveStudent] = useState(null);

  // Persist + restore the active student across hook instances (onboarding
  // and Home each create their own useStudents), so the child selected in
  // onboarding carries over to the home page display.
  const setActiveStudentPersisted = useCallback((student) => {
    setActiveStudent(student);
    storeActiveId(student?.id || null);
  }, []);

  const { data: students, isLoading } = useQuery({
    queryKey: ["students"],
    queryFn: async () => {
      if (!currentUser) return [];
      const studentList = await base44.entities.Student.list();
      if (!studentList || studentList.length === 0) return [];

      const studentsWithEmails = await Promise.all(studentList.map(async (s) => {
        if (!s.creator_email) {
          return await base44.entities.Student.update(s.id, { creator_email: currentUser.email });
        }
        return s;
      }));
      return studentsWithEmails;
    },
    enabled: !!currentUser,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (students && students.length > 0) {
      const storedId = getStoredActiveId();
      const match = students.find((s) => s.id === storedId) || students[0];
      setActiveStudent((prev) => (prev?.id === match.id ? prev : match));
      storeActiveId(match.id);
    } else if (students && students.length === 0 && activeStudent) {
      setActiveStudent(null);
      storeActiveId(null);
    }
  }, [students]);

  const onboardingComplete = useCallback(async ({ studentName, studentYear }) => {
    try {
      const newStudent = await base44.entities.Student.create({
        student_name: studentName,
        student_year: studentYear,
        creator_email: currentUser.email
      });
      queryClient.setQueryData(["students"], [newStudent]);
      setActiveStudentPersisted(newStudent);
    } catch (e) {
      console.error(e);
    }
  }, [currentUser, queryClient]);

  const addStudent = useCallback(async ({ studentName, studentYear }) => {
    // Check if a student with the same name already exists for this creator
    const existing = (students || []).find(s =>
      (s.student_name || "").toLowerCase() === (studentName || "").toLowerCase()
    );

    if (existing) {
      // Same name exists — update year if different, don't create new entry
      if (existing.student_year !== studentYear) {
        try {
          const updated = await base44.entities.Student.update(existing.id, {
            student_year: studentYear,
            student_name: studentName,
          });
          queryClient.setQueryData(["students"], (prev) =>
            (prev || []).map(s => s.id === updated.id ? updated : s)
          );
          setActiveStudentPersisted(updated);
          return updated;
        } catch (e) {
          console.error(e);
          return null;
        }
      }
      // Same name and year — just set as active
      setActiveStudentPersisted(existing);
      return existing;
    }

    // New student name — create a new entry
    const tempId = `temp_${Date.now()}`;
    const optimistic = { id: tempId, student_name: studentName, student_year: studentYear, creator_email: currentUser?.email };

    const prevStudents = queryClient.getQueryData(["students"]);
    queryClient.setQueryData(["students"], (prev) => [...(prev || []), optimistic]);
    setActiveStudentPersisted(optimistic);

    try {
      const newStudent = await base44.entities.Student.create({ student_name: studentName, student_year: studentYear, creator_email: currentUser.email });
      queryClient.setQueryData(["students"], (prev) => prev.map((s) => s.id === tempId ? newStudent : s));
      setActiveStudentPersisted(newStudent);
      return newStudent;
    } catch (e) {
      queryClient.setQueryData(["students"], prevStudents);
      setActiveStudent((prev) => prev?.id === tempId ? null : prev);
      storeActiveId(getStoredActiveId() === tempId ? null : getStoredActiveId());
      console.error(e);
      return null;
    }
  }, [students, currentUser, queryClient]);

  const deleteStudent = useCallback(async (student) => {
    const prevStudents = queryClient.getQueryData(["students"]);
    const remaining = (prevStudents || []).filter((s) => s.id !== student.id);

    if (remaining.length > 0) {
      queryClient.setQueryData(["students"], remaining);
      setActiveStudentPersisted(remaining[0]);
    } else {
      queryClient.setQueryData(["students"], []);
      setActiveStudentPersisted(null);
    }

    try {
      await base44.entities.Student.delete(student.id);
    } catch (e) {
      queryClient.setQueryData(["students"], prevStudents);
      setActiveStudentPersisted(student);
      console.error(e);
    }
  }, [queryClient]);

  const updateStudent = useCallback(async (studentName, studentYear) => {
    try {
      const updated = await base44.entities.Student.update(activeStudent.id, {
        student_year: studentYear,
        student_name: studentName,
        creator_email: activeStudent.creator_email || currentUser.email
      });
      setActiveStudentPersisted(updated);
      queryClient.setQueryData(["students"], (prev) => (prev || []).map((s) => s.id === updated.id ? updated : s));
      return updated;
    } catch (e) {
      console.error(e);
      return null;
    }
  }, [activeStudent, currentUser, queryClient]);

  const refresh = useCallback(async () => {
    await queryClient.refetchQueries({ queryKey: ["students"] });
  }, [queryClient]);

  return {
    students: students || null,
    activeStudent,
    setActiveStudent: setActiveStudentPersisted,
    isLoading,
    onboardingComplete,
    addStudent,
    deleteStudent,
    updateStudent,
    refresh,
  };
}